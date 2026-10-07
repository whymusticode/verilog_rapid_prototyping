"""Claude Code print-mode transport with live, reported token accounting.

The outer converter supplies the bubblewrap command, which runs
``claude -p --output-format stream-json --include-partial-messages``. Nothing
is estimated from text length. Assistant events carry only the usage snapshot
from the start of their response (output_tokens is a handful even after long
thinking), so each response's real output count comes from its raw
``message_delta`` stream event. The limit is checked on every update (one
response can overshoot). Token-by-token content deltas are dropped from the
trace because the assembled assistant events already contain that content.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path


def totals(usage: dict) -> dict:
    """Anthropic usage -> the Codex-style totals codex_run.Usage expects.

    Anthropic reports uncached input, cache writes and cache reads separately;
    cache writes count as uncached input (their premium is not weighted).
    """
    read = usage.get("cache_read_input_tokens", usage.get("cacheReadInputTokens", 0)) or 0
    written = usage.get("cache_creation_input_tokens", usage.get("cacheCreationInputTokens", 0)) or 0
    fresh = usage.get("input_tokens", usage.get("inputTokens", 0)) or 0
    return {"inputTokens": fresh + written + read, "cachedInputTokens": read,
            "outputTokens": usage.get("output_tokens", usage.get("outputTokens", 0)) or 0}


def describe(tool: dict) -> str:
    """One readable line for a tool call in convert.log."""
    name, given = tool.get("name", "?"), tool.get("input") or {}
    detail = (given.get("description") or given.get("command") or given.get("file_path")
              or given.get("path") or given.get("pattern") or given.get("prompt") or "")
    return f"{name}: {' '.join(str(detail).split())[:200]}"


def run(command: list[str], conversion: Path, prompt: str, usage, stop_process, log_path: Path,
        reasoning_effort: str | None = None) -> tuple[int, dict]:
    started = time.monotonic()
    inbox = queue.Queue()
    result = {"status": "failed", "budget": usage.budget,
              "requested_reasoning_effort": reasoning_effort,
              "weights": dict(zip(("input", "output", "cached"), usage.weights))}
    # Streamed chunks of one API response repeat its message id; keep the latest.
    messages: dict[str, dict] = {}
    current = None
    with log_path.open("a") as errors, (conversion / "agent_events.jsonl").open("w") as trace:
        # The prompt goes in on the command line; keep it with the conversation.
        trace.write(json.dumps({"elapsed": 0.0, "direction": "sent",
                                "message": {"type": "prompt", "text": prompt}}) + "\n")

        def note(text):
            minutes, seconds = divmod(int(time.monotonic() - started), 60)
            errors.write(f"[{minutes:3d}:{seconds:02d}] {text}\n")
            errors.flush()
        process = subprocess.Popen(command, cwd=conversion, text=True, bufsize=1,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=errors, start_new_session=True)

        def read():
            for line in process.stdout:
                inbox.put(line)
            inbox.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        code = 1
        try:
            while True:
                try:
                    line = inbox.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    code = process.wait()
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    errors.write(line)
                    continue
                kind = event.get("type")
                raw = event.get("event", {}) if kind == "stream_event" else {}
                if raw.get("type", "").startswith("content_block"):
                    continue
                trace.write(json.dumps({"elapsed": time.monotonic() - started,
                                        "direction": "received", "message": event}) + "\n")
                trace.flush()
                point = None
                if kind == "system" and event.get("subtype") == "init":
                    result["session_id"] = event.get("session_id")
                    result["effective_settings"] = {
                        key: event[key] for key in ("model", "cwd", "claude_code_version",
                                                    "permissionMode", "apiKeySource", "tools")
                        if key in event}
                elif kind == "assistant":
                    message = event.get("message", {})
                    for block in message.get("content", []):
                        if event.get("parent_tool_use_id"):
                            break
                        if block.get("type") == "text":
                            note(block.get("text", "").strip())
                        elif block.get("type") == "tool_use":
                            note("> " + describe(block))
                    if message.get("id") and message.get("usage") and message["id"] not in messages:
                        messages[message["id"]] = totals(message["usage"])
                        point = True
                elif kind == "user" and not event.get("parent_tool_use_id"):
                    for block in event.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("is_error"):
                            content = block.get("content")
                            text = content if isinstance(content, str) else " ".join(
                                part.get("text", "") for part in content or [] if isinstance(part, dict))
                            note("! " + " ".join(text.split())[:300])
                elif kind == "stream_event" and not event.get("parent_tool_use_id"):
                    if raw.get("type") == "message_start":
                        current = raw.get("message", {}).get("id")
                        if current and raw["message"].get("usage"):
                            messages[current] = totals(raw["message"]["usage"])
                            point = True
                    elif raw.get("type") == "message_delta" and current in messages:
                        # message_delta usage is cumulative for this response.
                        merged = {**raw.get("usage", {})}
                        known = messages[current]
                        messages[current] = {
                            "inputTokens": max(known["inputTokens"], totals(merged)["inputTokens"]),
                            "cachedInputTokens": max(known["cachedInputTokens"], totals(merged)["cachedInputTokens"]),
                            "outputTokens": max(known["outputTokens"], totals(merged)["outputTokens"])}
                        point = True
                elif kind == "result":
                    subtype = event.get("subtype", "")
                    result["status"] = "completed" if subtype == "success" and not event.get("is_error") else subtype or "failed"
                    for key in ("num_turns", "duration_ms", "duration_api_ms", "stop_reason"):
                        if key in event:
                            result[key] = event[key]
                    # modelUsage also covers subagents and side calls, so it is
                    # the authoritative final total when present.
                    per_model = event.get("modelUsage") or {}
                    if per_model:
                        result["model_usage"] = per_model
                        summed = {key: 0 for key in ("inputTokens", "cachedInputTokens", "outputTokens")}
                        for entry in per_model.values():
                            for key, value in totals(entry).items():
                                summed[key] += value
                        usage.update(summed)
                    elif event.get("usage"):
                        usage.update(totals(event["usage"]))
                    if isinstance(event.get("total_cost_usd"), (int, float)):
                        result["api_cost_estimate"] = {
                            "usd": event["total_cost_usd"],
                            "source": "Claude Code total_cost_usd",
                            "basis": "Claude Code's own per-model API price estimate; "
                                     "not subscription billing"}
                if point:
                    summed = {key: sum(m[key] for m in messages.values())
                              for key in ("inputTokens", "cachedInputTokens", "outputTokens")}
                    point = usage.update(summed)
                    with (conversion / "tokens.jsonl").open("a") as tokens:
                        tokens.write(json.dumps({"elapsed": time.monotonic() - started, **point}) + "\n")
                    if usage.budget and point["weighted_tokens"] >= usage.budget:
                        # Print mode has no turn/interrupt; stop the whole group.
                        result["status"] = "token_limit"
                        code = 124
                        break
        except KeyboardInterrupt:
            result["status"] = "interrupted"
            raise
        finally:
            if process.poll() is None:
                stop_process(process)
            reader.join(timeout=5)
            process.stdout.close()
            if code == 0 and result["status"] != "completed":
                code = 1
            result.update(usage.snapshot())
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (conversion / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return code, result
