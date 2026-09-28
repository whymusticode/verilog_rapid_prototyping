"""Codex app-server transport with live, reported token accounting.

The outer converter supplies the bubblewrap command. Nothing is estimated from
text length: limits are checked at server usage notifications (one response can
overshoot). All messages are retained, including failed tools and deltas.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path


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
        usage: Usage, stop_process, log_path: Path) -> tuple[int, dict]:
    started = time.monotonic()
    inbox = queue.Queue()
    result = {"status": "failed", "budget": usage.budget,
              "weights": dict(zip(("input", "output", "cached"), usage.weights))}
    with log_path.open("w") as errors, (conversion / "agent_events.jsonl").open("w") as trace:
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
                              "sandbox": "danger-full-access", "ephemeral": True}
                    if model:
                        params["model"] = model
                    send({"id": 1, "method": "thread/start", "params": params})
                elif message.get("id") == 1:
                    thread_id = message["result"]["thread"]["id"]
                    result["thread_id"] = thread_id
                    result["effective_settings"] = {
                        key: value for key, value in message["result"].items() if key != "thread"}
                    send({"id": 2, "method": "turn/start", "params": {
                        "threadId": thread_id, "input": [{"type": "text", "text": prompt}]}})
                method, params = message.get("method"), message.get("params", {})
                if method == "turn/started":
                    turn_id = params["turn"]["id"]
                if method == "thread/tokenUsage/updated":
                    point = usage.update(params["tokenUsage"]["total"])
                    with (conversion / "tokens.jsonl").open("a") as tokens:
                        tokens.write(json.dumps({"elapsed": time.monotonic() - started, **point}) + "\n")
                    if usage.budget and point["weighted_tokens"] >= usage.budget and interrupted_at is None:
                        result["status"] = "token_limit"
                        interrupted_at = time.monotonic()
                        send({"id": 3, "method": "turn/interrupt", "params": {
                            "threadId": thread_id, "turnId": params.get("turnId", turn_id)}})
                if method == "item/completed":
                    item = params.get("item", {})
                    if item.get("type") == "agentMessage":
                        errors.write(item.get("text", "") + "\n")
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
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (conversion / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    return code, result
