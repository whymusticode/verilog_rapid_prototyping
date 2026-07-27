"""Anthropic API wrapper with prompt caching, retries, and token accounting."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import anthropic

from .cache import advisory_lock, llm_cache_dir, read_json, stable_hash, write_json

# https://platform.claude.com/docs/en/about-claude/models/overview
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16384
in_price, out_price = 3.0, 15.0

MONITOR_LOG = "monitor.log"
LLM_CACHE_ENABLED = True
LLM_CACHE_BYPASS = False


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_creation_input_tokens += (
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )
        self.cache_read_input_tokens += (
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )

    def estimate_cost_usd(self) -> float:
        cache_write = self.cache_creation_input_tokens * (in_price * 1.25) / 1e6
        cache_read = self.cache_read_input_tokens * (in_price * 0.10) / 1e6
        regular_in = self.input_tokens * in_price / 1e6
        regular_out = self.output_tokens * out_price / 1e6
        return regular_in + regular_out + cache_write + cache_read


@dataclass
class ChatResult:
    response: Any
    text: str
    stop_reason: Optional[str]
    tool_uses: list[Any] = field(default_factory=list)


class Client:
    def __init__(
        self,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        max_retries: int = 4,
        monitor_log: str | os.PathLike | None = MONITOR_LOG,
        cache_enabled: bool = LLM_CACHE_ENABLED,
        cache_bypass: bool = LLM_CACHE_BYPASS,
    ):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._client = anthropic.Anthropic()
        self.usage = TokenUsage()
        self.monitor_log_path: Optional[Path] = (
            Path(monitor_log).resolve() if monitor_log else None
        )
        self._call_count: int = 0
        self._carry_over_calls: int = 0
        self.cache_enabled = cache_enabled
        self.cache_bypass = cache_bypass
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self._cache_dir: Path = llm_cache_dir()
        self._load_monitor_carry_over()

    def chat(
        self,
        messages: list[dict],
        *,
        system: Optional[list[dict] | str] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        max_tokens: Optional[int] = None,
        extra_headers: Optional[dict] = None,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        cache_key = self._request_cache_key(kwargs)
        cached_payload = self._cache_read(cache_key)
        if cached_payload is not None:
            self.cache_hits += 1
            print(f"[py2v-cache] llm cache hit: {self._cache_path(cache_key)}")
            return self._chat_result_from_cached(cached_payload)

        self.cache_misses += 1
        print(f"[py2v-cache] llm cache miss: {self._cache_path(cache_key)}")

        response = self._with_retry(self._client.messages.create, **kwargs)
        self.usage.add(response.usage)
        self._call_count += 1
        self._write_monitor(response.usage)
        self._cache_write(cache_key, kwargs, response)

        text_chunks: list[str] = []
        tool_uses: list[Any] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_chunks.append(block.text)
            elif btype == "tool_use":
                tool_uses.append(block)
        return ChatResult(
            response=response,
            text="".join(text_chunks),
            stop_reason=response.stop_reason,
            tool_uses=tool_uses,
        )

    def _load_monitor_carry_over(self) -> None:
        if self.monitor_log_path is None or not self.monitor_log_path.exists():
            return
        try:
            log_text = self.monitor_log_path.read_text()
        except OSError:
            return
        for line in reversed(log_text.splitlines()):
            if line.startswith("json: "):
                try:
                    payload = json.loads(line[len("json: ") :])
                except json.JSONDecodeError:
                    return
                tok = payload.get("cumulative_tokens", {})
                self.usage.input_tokens = int(tok.get("input", 0))
                self.usage.output_tokens = int(tok.get("output", 0))
                self.usage.cache_creation_input_tokens = int(
                    tok.get("cache_creation_input", 0)
                )
                self.usage.cache_read_input_tokens = int(tok.get("cache_read_input", 0))
                self._carry_over_calls = int(payload.get("calls", 0))
                return

    def _write_monitor(self, last_usage: Any) -> None:
        if self.monitor_log_path is None:
            return
        try:
            self.monitor_log_path.parent.mkdir(parents=True, exist_ok=True)
            cost = self.usage.estimate_cost_usd()
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "model": self.model,
                "calls": self._call_count + self._carry_over_calls,
                "cumulative_usd": round(cost, 6),
                "cache": {
                    "enabled": self.cache_enabled,
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                },
                "cumulative_tokens": {
                    "input": self.usage.input_tokens,
                    "output": self.usage.output_tokens,
                    "cache_creation_input": self.usage.cache_creation_input_tokens,
                    "cache_read_input": self.usage.cache_read_input_tokens,
                },
                "last_call": {
                    "input": getattr(last_usage, "input_tokens", 0) or 0,
                    "output": getattr(last_usage, "output_tokens", 0) or 0,
                    "cache_creation_input": getattr(
                        last_usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                    "cache_read_input": getattr(
                        last_usage, "cache_read_input_tokens", 0
                    )
                    or 0,
                },
            }
            text_block = (
                f"# py2v monitor.log -- {payload['timestamp']}\n"
                f"model: {payload['model']}\n"
                f"calls: {payload['calls']}\n"
                f"cumulative_cost_usd: ${payload['cumulative_usd']:.4f}\n"
                f"json: {json.dumps(payload)}\n"
            )
            self.monitor_log_path.write_text(text_block)
        except OSError:
            pass

    def _with_retry(self, fn, **kwargs):
        delay = 2.0
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                return fn(**kwargs)
            except (
                anthropic.APIConnectionError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
            ) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        assert last_exc is not None
        raise last_exc

    def _request_cache_key(self, kwargs: dict[str, Any]) -> str:
        payload = {
            "model": kwargs["model"],
            "max_tokens": kwargs["max_tokens"],
            "messages": kwargs["messages"],
            "system": kwargs.get("system"),
            "tools": kwargs.get("tools"),
            "tool_choice": kwargs.get("tool_choice"),
            "extra_headers": kwargs.get("extra_headers"),
        }
        return stable_hash(payload, namespace="llm-v1")

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _cache_read(self, cache_key: str) -> dict[str, Any] | None:
        if (not self.cache_enabled) or self.cache_bypass:
            return None
        path = self._cache_path(cache_key)
        lock_path = self._cache_dir / ".lock"
        with advisory_lock(lock_path):
            payload = read_json(path)
        if not payload or payload.get("schema") != "llm-cache-v1":
            return None
        return payload

    def _cache_write(self, cache_key: str, kwargs: dict[str, Any], response: Any) -> None:
        if (not self.cache_enabled) or self.cache_bypass:
            return
        record = {
            "schema": "llm-cache-v1",
            "cache_key": cache_key,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": self.model,
            "request": {
                "model": kwargs["model"],
                "max_tokens": kwargs["max_tokens"],
                "messages": kwargs["messages"],
                "system": kwargs.get("system"),
                "tools": kwargs.get("tools"),
                "tool_choice": kwargs.get("tool_choice"),
                "extra_headers": kwargs.get("extra_headers"),
            },
            "response": {
                "stop_reason": response.stop_reason,
                "content": [_serialize_content_block(block) for block in response.content],
                "usage": {
                    "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
                    "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
                    "cache_creation_input_tokens": getattr(
                        response.usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                    "cache_read_input_tokens": getattr(
                        response.usage, "cache_read_input_tokens", 0
                    )
                    or 0,
                },
            },
        }
        path = self._cache_path(cache_key)
        lock_path = self._cache_dir / ".lock"
        with advisory_lock(lock_path):
            if path.exists():
                return
            write_json(path, record)
        print(f"[py2v-cache] llm cache saved: {path}")

    def _chat_result_from_cached(self, payload: dict[str, Any]) -> ChatResult:
        resp = payload.get("response", {})
        content = [_hydrate_content_block(item) for item in resp.get("content", [])]
        text_chunks: list[str] = []
        tool_uses: list[Any] = []
        for block in content:
            if getattr(block, "type", None) == "text":
                text_chunks.append(block.text or "")
            elif getattr(block, "type", None) == "tool_use":
                tool_uses.append(block)
        usage_payload = resp.get("usage", {})
        response_obj = _MiniResponse(
            stop_reason=resp.get("stop_reason"),
            content=content,
            usage=_MiniUsage(
                input_tokens=int(usage_payload.get("input_tokens", 0)),
                output_tokens=int(usage_payload.get("output_tokens", 0)),
                cache_creation_input_tokens=int(
                    usage_payload.get("cache_creation_input_tokens", 0)
                ),
                cache_read_input_tokens=int(usage_payload.get("cache_read_input_tokens", 0)),
            ),
        )
        return ChatResult(
            response=response_obj,
            text="".join(text_chunks),
            stop_reason=response_obj.stop_reason,
            tool_uses=tool_uses,
        )


@dataclass
class _MiniUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _MiniContent:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


@dataclass
class _MiniResponse:
    stop_reason: str | None
    content: list[_MiniContent]
    usage: _MiniUsage


def _serialize_content_block(block: Any) -> dict[str, Any]:
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}) or {},
        }
    return {"type": "unknown"}


def _hydrate_content_block(payload: dict[str, Any]) -> _MiniContent:
    btype = payload.get("type", "unknown")
    if btype == "text":
        return _MiniContent(type="text", text=str(payload.get("text", "")))
    if btype == "tool_use":
        return _MiniContent(
            type="tool_use",
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            input=payload.get("input") or {},
        )
    return _MiniContent(type="unknown")


def cached(s: str) -> dict:
    return {"type": "text", "text": s, "cache_control": {"type": "ephemeral"}}


def text(text_str: str) -> dict:
    return {"type": "text", "text": text_str}


def strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s
