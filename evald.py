#!/usr/bin/env python3
"""Serve the evaluators to a sandboxed agent over a unix socket.

The agent never receives the FPGA toolchain. It sends {"tool": "sim"} and
gets the printed metrics back; simulation artifacts go into the writable
conversion directory for debugging. Keeping the evaluators here also lets a
single supervisor reap their process trees, including timed-out Vivado runs.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# Flags the agent may pass through. The service chooses the conversion's
# Python copy and RTL paths; agents cannot redirect an evaluator elsewhere.
ALLOWED = {"sim": {"--top", "--drain-stall", "--rate"},
           "synth": {"--top", "--implement", "--paths"}}
TOOL_GUIDE = """# Conversion evaluator tools

Run from the conversion root. These commands already connect to the host
toolchain; no server startup, package installation or socket probing is needed.

    sim                       # random frames, precision and cycle measurements
    sim --drain-stall 20       # additionally test randomized output backpressure
    sim --rate 50000000        # optional paced-input experiment (samples/second)
    synth                     # resource counts and synthesis-estimated Fmax
    synth --paths 5            # show worst timing paths to guide pipelining
    synth --implement         # place and route: measured routed timing

Both accept --top MODULE if automatic top detection is ambiguous. No positional
paths are needed or accepted. sim always uses this conversion's Python copy;
the runner separately tests the original Python when you finish.

An exit status of zero from sim means it obtained a measurement, not that the
design is good. Precision = log2(peak reference magnitude / RMS error).
Every additional bit matters: 14 bits is better than 13. Cycles, precision,
resources and Fmax are continuous measurements, without performance cutoffs.
First get the computation right and cycles low, then improve precision/resources;
timing closure is normally the last optimization step. Stimuli are
fresh and unseeded. Frame boundaries and state reset must match target(x).
By default input is unthrottled so cycles/frame measures design capacity rather
than an input generator deliberately paced at the target. --rate sets a paced run.

IO/tb.sv contains the actual instantiated widths/FRAC, AXI signal names and
testbench. IO/vectors.hex and input.log/output.log hold packed lane values and
transfer cycles. IO/errors.json holds worst numerical mismatches if available.
Lane 0 is least significant; complex values pack real then imaginary lanes.
FRAC is dynamic. N is the frame length, not the inner algorithm block size.

Synthesis Fmax is an estimate until --implement routes the design. A successful
tool execution does not alone imply timing closure: compare Fmax with target
frequency. LUT/DSP/RAM report used, available and percentage. Serial evaluations
can take several minutes; wait for the current command, do not start another.

Each evaluation is archived in evaluations/ with sources, inputs, outputs,
reports, source hashes and a result.json. evald.jsonl links these to token usage.
"""
# Backstops around each evaluator's own budget, not a replacement for it.
TIMEOUT = {"sim": 300.0, "synth": 900.0}
PR_SET_CHILD_SUBREAPER = 36

# Pulled out of the evaluators' own printed metrics so a run leaves behind a
# machine-readable trail: one JSON object per evaluation, in call order.
METRICS = {
    "precision_bits": r"bits of precision:\s*(-?[\d.]+(?:e[+-]?\d+)?|inf|-inf)",
    "rmse": r"RMS error:\s*([\d.]+(?:e[+-]?\d+)?)",
    "cycles_per_frame": r"throughput:\s*([\d.]+) cycles/frame",
    "latency_cycles": r"latency:\s*(\d+) cycles",
    "fraction_bits": r"fraction bits:\s*(\d+)",
    "lut": r"LUT:\s*(\d+)",
    "dsp": r"DSP:\s*(\d+)",
    "ram": r"RAM:\s*([\d.]+)",
    "fmax_mhz": r"Fmax:\s*([\d.]+)",
    "seconds": r"evaluation time:\s*([\d.]+)s",
}


def measurements(printed: str) -> dict:
    """Scrape the numbers an evaluator printed. Absent keys simply stay out."""
    found = {}
    for name, pattern in METRICS.items():
        match = re.search(pattern, printed)
        if match:
            text = match.group(1)
            if text in ("inf", "-inf"):
                # A bit-exact result has no error to take the log of. Say so
                # explicitly rather than emitting a non-finite JSON number.
                found["precision_bits"], found["exact"] = None, text == "inf"
            else:
                found[name] = float(text) if "." in text or "e" in text else int(text)
    return found


class Recorder:
    """Archive exactly the sources evaluated, full feedback, and token position."""
    def __init__(self, project: Path, output: Path, usage=None):
        self.project, self.output, self.usage = project, output, usage
        self.lock = threading.Lock()
        self.index = max((int(p.name.split("_", 1)[0])
                          for p in (output.parent / "evaluations").glob("[0-9]*_*")
                          if p.name.split("_", 1)[0].isdigit()), default=0)
        self.started = time.monotonic()

    def evaluate(self, tool: str, extra: list[str], reference="copied") -> dict:
        with self.lock:
            self.index += 1
            conversion = self.output.parent
            archive = conversion / "evaluations" / f"{self.index:03d}_{tool}_{reference}"
            archive.mkdir(parents=True)
            for source, destination in ((self.output, archive / "rtl"),
                                        (conversion / "python", archive / "python")):
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if reference == "original":
                shutil.copytree(self.project, archive / "original_reference",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if tool == "synth" and (conversion / "IO" / "tb.sv").exists():
                (archive / "IO").mkdir()
                shutil.copy2(conversion / "IO" / "tb.sv", archive / "IO" / "tb.sv")
            manifest = {str(p.relative_to(archive)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for base in (archive / "rtl", archive / "python", archive / "original_reference")
                        for p in sorted(base.rglob("*")) if p.is_file()}
            rtl_hash = hashlib.sha256(json.dumps({k: v for k, v in manifest.items()
                                                if k.startswith("rtl/")}, sort_keys=True).encode()).hexdigest()
            point = self.usage.snapshot() if self.usage else {}
            entry = {"project": self.project.name, "tool": tool, "attempt": self.index,
                     "reference": reference, "args": extra, "rtl_sha256": rtl_hash,
                     "archive": str(archive.relative_to(conversion)),
                     "elapsed_start": time.monotonic() - self.started, **point}
            entry["evaluator_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                         for name in (f"{tool}.py", "vrp.py")}
            (archive / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            actual = [*extra]
            if reference == "original":
                if tool == "sim":
                    actual.insert(0, str(self.project))
                else:
                    actual.extend(("--project", str(self.project)))
            if tool == "synth":
                actual.extend(("--work", str(archive / "synthesis")))
            code, printed = evaluate(tool, actual, archive / "rtl")
            (archive / "output.log").write_text(printed)
            if tool == "sim" and reference == "copied" and (archive / "IO").exists():
                shutil.copytree(archive / "IO", conversion / "IO", dirs_exist_ok=True)
            entry.update({"exit": code, "elapsed": time.monotonic() - self.started,
                          **measurements(printed)})
            if tool == "synth":
                entry["timing_stage"] = "routed" if "--implement" in extra else "synthesis_estimate"
            (archive / "result.json").write_text(json.dumps(entry, indent=2) + "\n")
            record(conversion / "evald.jsonl", entry)
            return {"exit": code, "output": printed, "record": entry}


def become_subreaper() -> None:
    """Adopt orphaned grandchildren instead of letting them reach init.

    Vivado runs behind ``nix run`` and a second bubblewrap layer, which breaks
    the process group.  Without this, a timed-out run leaves the real work
    running at full CPU indefinitely and every later run is slower for it.
    """
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(
            PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
    except (OSError, AttributeError):
        pass


def descendants(root: int) -> list[int]:
    """Every live process below ``root``, by walking /proc.

    Ancestry rather than command-line matching is deliberate: a pattern like
    "vivado" also matches an editor that merely has such a path open.
    """
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        # comm sits in parentheses and may itself contain spaces or brackets,
        # so the fields have to be read after the final one.
        try:
            parent = int(stat[stat.rindex(")") + 2:].split()[1])
        except (ValueError, IndexError):
            continue
        children.setdefault(parent, []).append(int(entry.name))
    found: list[int] = []
    queue = [root]
    while queue:
        for child in children.get(queue.pop(), []):
            found.append(child)
            queue.append(child)
    return found


def kill_tree(pid: int) -> None:
    """Stop a process and everything it spawned, politely and then not."""
    targets = [pid, *descendants(pid)]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for target in targets:
            try:
                os.kill(target, sig)
            except (ProcessLookupError, PermissionError):
                pass
        if sig is signal.SIGTERM:
            time.sleep(2.0)
            # Re-scan: the container layers spawn helpers while shutting down.
            targets = [pid, *descendants(pid)]


def record(log: Path | None, entry: dict) -> None:
    """Append one evaluation to the run's JSONL trail, best effort."""
    if log is None:
        return
    try:
        with log.open("a") as stream:
            stream.write(json.dumps(entry, allow_nan=False) + "\n")
    except OSError:
        pass


def evaluate(tool: str, extra: list[str], output: Path) -> tuple[int, str]:
    """Run one evaluator to completion and return its status and output."""
    command = [sys.executable, str(ROOT / f"{tool}.py"), str(output.parent)]
    command.extend(extra)
    try:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(command, cwd=output.parent, text=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   env=environment,
                                   start_new_session=True)
    except OSError as error:
        return 1, f"cannot start {tool}: {error}\n"
    try:
        printed, _ = process.communicate(timeout=TIMEOUT[tool])
    except subprocess.TimeoutExpired:
        kill_tree(process.pid)
        printed, _ = process.communicate()
        return 1, (printed + f"\n{tool} exceeded the {TIMEOUT[tool]:g}s service limit "
                   f"and was stopped\n")
    return process.returncode, printed


def handle(payload: dict, project: Path, output: Path, recorder=None) -> dict:
    """Validate one request and answer it."""
    tool = payload.get("tool")
    if tool not in ALLOWED:
        return {"exit": 2, "output": f"unknown evaluator: {tool!r}\n"}
    extra = [str(item) for item in payload.get("args", [])]
    index = 0
    while index < len(extra):
        flag = extra[index]
        if flag not in ALLOWED[tool]:
            return {"exit": 2, "output": f"unsupported argument: {flag}; use {tool} --help\n"}
        index += 1
        if flag != "--implement":
            if index == len(extra) or extra[index].startswith("-"):
                return {"exit": 2, "output": f"{flag} requires a value\n"}
            index += 1
    if recorder:
        return recorder.evaluate(tool, extra)
    code, printed = evaluate(tool, extra, output)
    return {"exit": code, "output": printed}


def serve(socket_path: Path, project: Path, output: Path,
          log: Path | None = None, recorder=None, ready=None) -> None:
    """Answer evaluation requests on ``socket_path`` until the process ends."""
    become_subreaper()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.listen(4)
    if ready:
        ready.set()
    # One evaluation at a time: concurrent synthesis runs starve each other and
    # make the reported numbers depend on what else happened to be running.
    running = threading.Lock()
    attempts = {tool: 0 for tool in ALLOWED}
    started = time.time()

    def answer(conn: socket.socket) -> None:
        with conn:
            try:
                chunks = []
                while not chunks or not chunks[-1].endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                payload = json.loads(b"".join(chunks) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("request must be a JSON object")
            except (OSError, ValueError) as error:
                payload = None
                reply = {"exit": 2, "output": f"malformed request: {error}\n"}
            if payload is not None:
                with running:
                    tool = payload.get("tool")
                    try:
                        reply = handle(payload, project, output, recorder)
                    except Exception as error:
                        reply = {"exit": 1, "output": f"evaluation service: {type(error).__name__}: {error}\n"}
                    if tool in attempts and recorder is None:
                        attempts[tool] += 1
                        entry = {"project": project.name, "output": str(output),
                                 "tool": tool, "attempt": attempts[tool],
                                 "elapsed": round(time.time() - started, 1),
                                 "exit": reply["exit"]}
                        entry.update(measurements(reply["output"]))
                        if reply["exit"]:
                            entry["error"] = reply["output"].strip().splitlines()[-1][:200] \
                                if reply["output"].strip() else ""
                        record(log, entry)
            try:
                conn.sendall(json.dumps(reply).encode())
            except OSError:
                pass

    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            return
        threading.Thread(target=answer, args=(conn,), daemon=True).start()


CLIENT = '''#!/usr/bin/env python3
"""Forward one evaluation request to the service outside the sandbox."""
import json
import socket
import sys

SOCKET = {socket!r}
if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
    print({guide!r})
    raise SystemExit(0)
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    client.connect(SOCKET)
    client.sendall(json.dumps({{"tool": {tool!r}, "args": sys.argv[1:]}}).encode() + b"\\n")
    client.shutdown(socket.SHUT_WR)
    chunks = []
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
except OSError as error:
    print(f"cannot reach the evaluation service: {{error}}", file=sys.stderr)
    raise SystemExit(70)
reply = json.loads(b"".join(chunks) or b'{{"exit": 70, "output": "empty reply"}}')
print(reply.get("output", ""), end="")
raise SystemExit(int(reply.get("exit", 70)))
'''


def install_clients(bin_dir: Path, socket_path: Path) -> None:
    """Write the `sim` and `synth` stubs the sandboxed agent calls."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool in ALLOWED:
        stub = bin_dir / tool
        stub.write_text(CLIENT.format(socket=str(socket_path), tool=tool, guide=TOOL_GUIDE))
        stub.chmod(0o755)
