"""LLM tool-use loop driver.

Iterates the model with a tool catalog until one of:
  - the model emits `end_turn` with no further tool calls
  - a per-loop success predicate returns True
  - the round / token budget is exhausted

Every turn is appended to `<build>/transcript.jsonl` for resume + audit.
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .client import Client
from .tools import Tool


# The text editor tool is GA on Claude 4.x; no beta header is needed.
# If a future / preview model requires one, set ANTHROPIC_BETA_HEADERS
# (comma-separated) in the environment.


@dataclass
class StopReason:
    code: str  # "success" | "end_turn" | "max_rounds" | "token_budget" | "stuck" | "error"
    detail: str = ""


@dataclass
class AgentRun:
    rounds: int = 0
    stop_reason: Optional[StopReason] = None
    last_text: str = ""
    success: bool = False
    transcript_path: Optional[Path] = None


def _serialize_tool_use(block) -> dict:
    return {
        "type": "tool_use",
        "id": block.id,
        "name": block.name,
        "input": block.input,
    }


def _serialize_text(block) -> dict:
    return {"type": "text", "text": block.text}


def _serialize_response(content) -> list[dict]:
    out: list[dict] = []
    for b in content:
        t = getattr(b, "type", None)
        if t == "text":
            out.append(_serialize_text(b))
        elif t == "tool_use":
            out.append(_serialize_tool_use(b))
    return out


def run_agent(
    *,
    client: Client,
    system_prompt: str | list[dict],
    seed_user_message: str | list[dict],
    tools: list[Tool],
    transcript_path: Path,
    max_rounds: int = 20,
    token_budget_usd: float = 5.0,
    success_check: Optional[Callable[[Any, dict], bool]] = None,
    stuck_signature: Optional[Callable[[dict], str]] = None,
    stuck_threshold: int = 3,
) -> AgentRun:
    """Run the tool-use loop.

    `success_check(last_chat_result, last_tool_results)` is invoked after each
    round; returning True ends the loop with stop_reason="success".

    `stuck_signature(last_tool_results)` returns a string. If the same string
    is observed `stuck_threshold` rounds in a row, the loop ends with
    stop_reason="stuck".
    """
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript = open(transcript_path, "a", buffering=1)

    extra_headers = None
    beta_env = os.environ.get("ANTHROPIC_BETA_HEADERS", "").strip()
    if beta_env:
        extra_headers = {"anthropic-beta": beta_env}

    tool_schemas = [t.schema for t in tools]
    tool_by_name = {t.name: t for t in tools}

    if isinstance(seed_user_message, str):
        user_content: list[dict] = [{"type": "text", "text": seed_user_message}]
    else:
        user_content = list(seed_user_message)
    messages: list[dict] = [{"role": "user", "content": user_content}]
    transcript.write(json.dumps({"event": "user_seed", "content": user_content}) + "\n")

    run = AgentRun(transcript_path=transcript_path)
    last_signatures: list[str] = []
    last_chat = None
    last_tool_results: dict = {}

    try:
        for round_idx in range(max_rounds):
            run.rounds = round_idx + 1
            cost = client.usage.estimate_cost_usd(client.model)
            if cost >= token_budget_usd:
                run.stop_reason = StopReason(
                    code="token_budget",
                    detail=f"estimated cost ${cost:.2f} >= budget ${token_budget_usd:.2f}",
                )
                break

            chat = client.chat(
                messages=messages,
                system=system_prompt,
                tools=tool_schemas,
                extra_headers=extra_headers,
            )
            last_chat = chat
            run.last_text = chat.text or run.last_text

            transcript.write(
                json.dumps(
                    {
                        "event": "assistant",
                        "round": run.rounds,
                        "stop_reason": chat.stop_reason,
                        "content": _serialize_response(chat.response.content),
                        "usage": {
                            "input_tokens": getattr(chat.response.usage, "input_tokens", 0),
                            "output_tokens": getattr(chat.response.usage, "output_tokens", 0),
                            "cache_creation": getattr(
                                chat.response.usage, "cache_creation_input_tokens", 0
                            ),
                            "cache_read": getattr(
                                chat.response.usage, "cache_read_input_tokens", 0
                            ),
                        },
                    }
                )
                + "\n"
            )

            messages.append(
                {"role": "assistant", "content": _serialize_response(chat.response.content)}
            )

            if not chat.tool_uses:
                run.stop_reason = StopReason(code="end_turn", detail=chat.stop_reason or "")
                break

            tool_results: list[dict] = []
            this_round_results: dict = {}
            for tu in chat.tool_uses:
                tool = tool_by_name.get(tu.name)
                if tool is None:
                    payload = {"error": f"unknown tool: {tu.name}"}
                else:
                    try:
                        payload = tool.handler(tu.input)
                    except Exception as exc:
                        payload = {"error": f"tool raised: {type(exc).__name__}: {exc}"}
                this_round_results[tu.name] = payload
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": _stringify_payload(payload),
                    }
                )
                transcript.write(
                    json.dumps(
                        {
                            "event": "tool_result",
                            "round": run.rounds,
                            "tool": tu.name,
                            "id": tu.id,
                            "input": tu.input,
                            "result": payload,
                        }
                    )
                    + "\n"
                )

            messages.append({"role": "user", "content": tool_results})
            last_tool_results = this_round_results

            if success_check is not None and success_check(chat, this_round_results):
                run.success = True
                run.stop_reason = StopReason(code="success")
                break

            if stuck_signature is not None:
                sig = stuck_signature(this_round_results)
                last_signatures.append(sig)
                last_signatures = last_signatures[-stuck_threshold:]
                if len(last_signatures) == stuck_threshold and len(set(last_signatures)) == 1:
                    run.stop_reason = StopReason(code="stuck", detail=f"sig={sig}")
                    break
        else:
            run.stop_reason = StopReason(code="max_rounds", detail=f"hit {max_rounds}")
    finally:
        transcript.write(
            json.dumps(
                {
                    "event": "end",
                    "rounds": run.rounds,
                    "stop_reason": dataclasses.asdict(run.stop_reason)
                    if run.stop_reason
                    else None,
                    "success": run.success,
                    "usage": dataclasses.asdict(client.usage),
                    "estimated_cost_usd": round(client.usage.estimate_cost_usd(client.model), 4),
                }
            )
            + "\n"
        )
        transcript.close()

    return run


def _stringify_payload(payload: Any) -> str:
    """Tool results must be string content for Anthropic. Emit JSON for dicts."""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, indent=2, default=str)
    except (TypeError, ValueError):
        return str(payload)
