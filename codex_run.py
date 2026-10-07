"""Codex app-server transport with live, reported token accounting.

The outer converter supplies the bubblewrap command. Nothing is estimated from
text length: limits are checked at server usage notifications (one response can
overshoot). All messages are retained, including failed tools and deltas.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path


def api_cost_estimate(model: str, usage: dict) -> dict | None:
    """Standard short-context text rates; not a Codex subscription invoice."""
    if model != "gpt-6-luna":
        return None
    uncached = usage.get("input_tokens", 0) - usage.get("cached_input_tokens", 0)
    dollars = (uncached * .10 + usage.get("cached_input_tokens", 0) * .01
               + usage.get("output_tokens", 0) * .50) / 1_000_000
    return {"usd": round(dollars, 10),
            "usd_per_million": {"uncached_input": .10, "output": .50, "cached_input": .01},
            "source": "https://developers.openai.com/api/docs/models/gpt-6-luna",
            "verified_on": "2026-09-28",
            "basis": "Standard short-context text tokens; excludes unreported cache-write premiums, "
                     "service-tier/regional adjustments and tool fees; not actual Codex billing"}


class Usage:
    def __init__(self, budget: float, weights: list[float]):
        self.budget, self.weights = budget, weights
        self.lock = threading.Lock()
        self.value = {"input_tokens": 0, "cached_input_tokens": 0,
                      "output_tokens": 0, "weighted_tokens": 0.0}

    def update(self, total: dict) -> dict:
        incoming = total["inputTokens"]
        cached = total["cachedInputTokens"]
        outgoing = total["outputTokens"]
        wi, wo, wc = self.weights
        with self.lock:
            self.value = {"input_tokens": incoming, "cached_input_tokens": cached,
                          "output_tokens": outgoing,
                          "reasoning_output_tokens": total.get("reasoningOutputTokens", 0),
                          "weighted_tokens": round(wi * (incoming - cached)
                                                   + wo * outgoing + wc * cached, 3)}
            return dict(self.value)

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.value)


def run(command: list[str], conversion: Path, prompt: str, model: str,
        usage: Usage, stop_process, log_path: Path,
        reasoning_effort: str | None = None, resume_thread: str | None = None,
        on_thread=None) -> tuple[int, dict]:
    """Run one turn on a new thread, or on ``resume_thread`` when given.

    ``on_thread`` receives the thread id as soon as the server assigns it.
    """
    started = time.monotonic()
    inbox = queue.Queue()
    result = {"status": "failed", "budget": usage.budget,
              "requested_reasoning_effort": reasoning_effort,
              "weights": dict(zip(("input", "output", "cached"), usage.weights))}
    with log_path.open("a") as errors, (conversion / "agent_events.jsonl").open("w") as trace:
        process = subprocess.Popen(command, cwd=conversion, text=True, bufsize=1,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors, start_new_session=True)

        def read():
            for line in process.stdout:
                inbox.put(line)
            inbox.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def send(message):
            trace.write(json.dumps({"elapsed": time.monotonic() - started,
                                    "direction": "sent", "message": message}) + "\n")
            trace.flush()
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        send({"id": 0, "method": "initialize", "params": {
            "clientInfo": {"name": "vrp", "version": "1.0"}}})
        thread_id = turn_id = None
        interrupted_at = None
        baseline = None
        code = 1
        try:
            while True:
                if interrupted_at is not None and time.monotonic() - interrupted_at > 10:
                    code = 124
                    break
                try:
                    line = inbox.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    errors.write(line)
                    continue
                trace.write(json.dumps({"elapsed": time.monotonic() - started,
                                        "direction": "received", "message": message}) + "\n")
                trace.flush()
                if "error" in message and "id" in message:
                    errors.write(json.dumps(message) + "\n")
                    result["error"] = message["error"]
                    break
                if message.get("id") == 0:
                    send({"method": "initialized", "params": {}})
                    params = {"cwd": str(conversion), "approvalPolicy": "never",
                              "sandbox": "danger-full-access"}
                    if model:
                        params["model"] = model
                    if reasoning_effort is not None:
                        params["config"] = {"model_reasoning_effort": reasoning_effort}
                    if resume_thread:
                        send({"id": 1, "method": "thread/resume", "params": {
                            **params, "threadId": resume_thread, "excludeTurns": True}})
                    else:
                        send({"id": 1, "method": "thread/start", "params": params})
                elif message.get("id") == 1:
                    thread_id = message["result"]["thread"]["id"]
                    result["thread_id"] = thread_id
                    if on_thread:
                        on_thread(thread_id)
                    result["effective_settings"] = {
                        key: value for key, value in message["result"].items() if key != "thread"}
                    send({"id": 2, "method": "turn/start", "params": {
                        "threadId": thread_id, "input": [{"type": "text", "text": prompt}]}})
                method, params = message.get("method"), message.get("params", {})
                if method == "turn/started":
                    turn_id = params["turn"]["id"]
                if method == "thread/tokenUsage/updated":
                    total, last = params["tokenUsage"]["total"], params["tokenUsage"].get("last")
                    if baseline is None:
                        # A resumed thread's totals include earlier runs; the
                        # budget covers this run, so count from before its first response.
                        baseline = {key: total[key] - last.get(key, 0) for key in total} if last else {}
                    point = usage.update({key: total[key] - baseline.get(key, 0) for key in total})
                    with (conversion / "tokens.jsonl").open("a") as tokens:
                        tokens.write(json.dumps({"elapsed": time.monotonic() - started, **point}) + "\n")
                    if usage.budget and point["weighted_tokens"] >= usage.budget and interrupted_at is None:
                        result["status"] = "token_limit"
                        interrupted_at = time.monotonic()
                        send({"id": 3, "method": "turn/interrupt", "params": {
                            "threadId": thread_id, "turnId": params.get("turnId", turn_id)}})
                if method == "item/completed":
                    item = params.get("item", {})
                    minutes, seconds = divmod(int(time.monotonic() - started), 60)
                    line = None
                    if item.get("type") == "agentMessage":
                        line = item.get("text", "").strip()
                    elif item.get("type") == "commandExecution":
                        shown = str(item.get("command", ""))
                        wrapped = re.match(r"\S*bash -lc (.+)$", shown, re.S)
                        if wrapped:
                            try:
                                shown = shlex.split(wrapped.group(1))[0]
                            except ValueError:
                                pass
                        line = "> " + " ".join(shown.split())[:200]
                        if item.get("exitCode") not in (None, 0):
                            line += f"  (exit {item['exitCode']})"
                    elif item.get("type") == "fileChange":
                        line = "> edit " + " ".join(
                            os.path.relpath(change.get("path", ""), conversion)
                            for change in item.get("changes", []))
                    if line:
                        errors.write(f"[{minutes:3d}:{seconds:02d}] {line}\n")
                        errors.flush()
                if method == "turn/completed":
                    if interrupted_at is None:
                        result["status"] = params["turn"]["status"]
                    code = 124 if interrupted_at is not None else (0 if result["status"] == "completed" else 1)
                    if params["turn"].get("error"):
                        result["error"] = params["turn"]["error"]
                    break
                if "id" in message and method:
                    # An unattended run must never wait forever on an input/approval request.
                    send({"id": message["id"], "error": {
                        "code": -32601, "message": "Interactive requests are unavailable in conversion runs"}})
        finally:
            if process.poll() is None:
                stop_process(process)
            reader.join(timeout=5)
            process.stdin.close()
            process.stdout.close()
            result.update(usage.snapshot())
            effective_model = result.get("effective_settings", {}).get("model", model)
            estimate = api_cost_estimate(effective_model, result)
            if estimate is not None:
                result["api_cost_estimate"] = estimate
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (conversion / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return code, result
