#!/usr/bin/env python3
"""Serve the evaluators to a sandboxed agent over a unix socket.

The agent never receives the FPGA toolchain. It sends {"tool": "sim"} and
gets the printed metrics back; simulation artifacts go into the writable
conversion directory for debugging. Keeping the evaluators here also lets a
single supervisor reap their process trees, including timed-out Vivado runs.
"""

from __future__ import annotations

# How many toolchain jobs run at once: sim, synth, direct Vivado commands and
# Tcl session commands all count. Each Vivado process takes a few GB.
MAX_JOBS = 2
# Persistent Tcl sessions an agent may keep open; idle ones hold memory only.
MAX_TCL_SESSIONS = 4

import ctypes
import hashlib
import json
import os
import queue
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import xilinx


ROOT = Path(__file__).resolve().parent

# Flags the agent may pass through. The service chooses the conversion's
# Python copy and RTL paths; agents cannot redirect an evaluator elsewhere.
ALLOWED = {"sim": {"--top", "--drain-stall", "--rate", "--samples"},
           "synth": {"--top", "--implement", "--paths"}}
# The agent-facing tool guide; also each stub's --help text.
TOOL_GUIDE = (ROOT / "prompts" / "tool_guide.md").read_text()
# Backstops around each evaluator's own budget, not a replacement for it.
TIMEOUT = {"sim": None, "synth": None}  # None: wait as long as it takes
# Xilinx programs the agent runs directly, jailed to its conversion directory.
# Their results are exploratory: only sim and synth produce recorded measurements.
PROGRAMS = ("vivado", "xvlog", "xvhdl", "xelab", "xsim")
PR_SET_CHILD_SUBREAPER = 36

# Pulled out of the evaluators' own printed metrics so a run leaves behind a
# machine-readable trail: one JSON object per evaluation, in call order.
METRICS = {
    "precision_bits": r"bits of precision:\s*(-?[\d.]+(?:e[+-]?\d+)?|inf|-inf)",
    "rmse": r"RMS error:\s*([\d.]+(?:e[+-]?\d+)?)",
    "cycles_per_sample": r"throughput:\s*([\d.]+(?:e[+-]?\d+)?) cycles/sample",
    "latency_cycles": r"latency:\s*(\d+) cycles",
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
    primary = re.search(r"^measurement group: (.+)$", printed, re.M)
    if primary:
        found["measurement_group"] = primary.group(1)
    groups = {}
    for match in re.finditer(r"^output group (.+): (\d+) mismatches / (\d+) samples; RMSE=(\S+)$", printed, re.M):
        name, mismatches, samples, rmse = match.groups()
        groups[name] = {"mismatches": int(mismatches), "samples": int(samples),
                        "rmse": None if rmse == "None" else float(rmse)}
    if groups:
        found["output_groups"] = groups
    return found


class Recorder:
    """Run evaluations in the conversion directory and log each one.

    Every call appends a record to evald.jsonl (measurements, RTL hash, token
    position) and a one-line summary to the run log. Artifacts are not
    snapshotted: IO/ and synthesis/ always hold the latest evaluation.
    """
    def __init__(self, project: Path, output: Path, usage=None, log: Path | None = None):
        self.project, self.output, self.usage, self.log = project, output, usage, log
        self.lock = threading.Lock()
        # sim writes IO/ and synth writes synthesis/, so each tool runs one at a
        # time; a sim and a synth may overlap.
        self.tool_locks = {tool: threading.Lock() for tool in ALLOWED}
        trail = output.parent / "evald.jsonl"
        self.index = len(trail.read_text().splitlines()) if trail.exists() else 0
        self.started = time.monotonic()

    def evaluate(self, tool: str, extra: list[str], reference="copied") -> dict:
        with self.tool_locks[tool]:
            with self.lock:
                self.index += 1
                attempt = self.index
            conversion = self.output.parent
            sources = {str(p.relative_to(self.output)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(self.output.rglob("*")) if p.is_file()}
            point = self.usage.snapshot() if self.usage else {}
            entry = {"project": self.project.name, "tool": tool, "attempt": attempt,
                     "reference": reference, "args": extra,
                     "rtl_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
                     "elapsed_start": time.monotonic() - self.started, **point}
            entry["evaluator_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                         for name in (f"{tool}.py", "vrp.py")}
            # The host evaluators write here; never follow links the agent planted.
            for directory in (conversion / "IO", conversion / "synthesis"):
                if directory.is_symlink():
                    directory.unlink()
                elif directory.is_dir():
                    for parent, folders, files in os.walk(directory):
                        for name in folders + files:
                            if os.path.islink(os.path.join(parent, name)):
                                os.unlink(os.path.join(parent, name))
            actual = [*extra]
            if reference == "original":
                if tool == "sim":
                    actual.insert(0, str(self.project))
                else:
                    actual.extend(("--project", str(self.project)))
            if tool == "synth":
                actual.extend(("--work", str(conversion / "synthesis")))
            code, printed = evaluate(tool, actual, self.output)
            entry.update({"exit": code, "elapsed": time.monotonic() - self.started,
                          **measurements(printed)})
            if code:
                entry["error"] = first_error(printed)
            if tool == "synth":
                entry["timing_stage"] = "routed" if "--implement" in extra else "synthesis_estimate"
            with self.lock:
                record(conversion / "evald.jsonl", entry)
                self.summarize(entry)
            return {"exit": code, "output": printed, "record": entry}

    def summarize(self, entry: dict) -> None:
        shown = ["precision_bits=inf (bit-exact)"] if entry.get("exact") else []
        shown += [f"{key}={entry[key]}" for key in (
            "precision_bits", "cycles_per_sample", "latency_cycles", "lut", "dsp", "ram",
            "fmax_mhz", "seconds", "error") if entry.get(key) is not None]
        line = (f"[evald #{entry['attempt']} {' '.join([entry['tool'], *entry['args']])}"
                f" ({entry['reference']}) exit {entry['exit']}] {' '.join(shown)}")
        print(line, flush=True)
        if self.log:
            with self.log.open("a") as stream:
                stream.write(line + "\n")


def first_error(printed: str) -> str:
    """The first line that names an error, else the last line, for the trail."""
    lines = [line.strip() for line in printed.splitlines() if line.strip()]
    for line in lines:
        if re.search(r"\berror\b|Error|ERROR|Traceback", line):
            return line[:300]
    return lines[-1][:300] if lines else ""


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
    """Append one evaluation to the run's JSONL trail, best effort.

    The trail lives in the agent's directory; never follow a link it planted."""
    if log is None:
        return
    try:
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o644)
        with os.fdopen(descriptor, "a") as stream:
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


class Stream:
    """One streamed reply: JSON lines of {"out": text}, then {"exit": code}.

    The client keeps its end open while it waits, so a closed connection means
    the caller gave up (Ctrl-C, its own shell timeout) and the job can stop."""
    def __init__(self, conn: socket.socket):
        self.conn, self.closed = conn, threading.Event()
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        try:
            while self.conn.recv(4096):
                pass
        except OSError:
            pass
        self.closed.set()

    def send(self, **message) -> None:
        if self.closed.is_set():
            return
        try:
            self.conn.sendall(json.dumps(message).encode() + b"\n")
        except OSError:
            self.closed.set()


def inside(path: str | None, conversion: Path) -> Path | None:
    """Resolve the caller's working directory; it must lie in the conversion."""
    resolved = Path(path or conversion).resolve()
    return resolved if resolved == conversion or conversion in resolved.parents else None


class Toolbox:
    """Direct Xilinx commands and persistent Tcl sessions for one conversion."""
    def __init__(self, conversion: Path, log: Path | None = None):
        self.conversion = conversion.resolve()
        self.log = log
        self.jobs = threading.BoundedSemaphore(MAX_JOBS)
        self.sessions: dict[str, TclSession] = {}
        self.lock = threading.Lock()
        # Tcl code travels through files only the host can write.
        self.code_dir = Path(tempfile.mkdtemp(prefix="vrp-tcl-"))
        self.started = time.monotonic()

    def note(self, entry: dict) -> None:
        entry["elapsed_start"] = round(time.monotonic() - self.started, 1)
        record(self.conversion / "vivado_commands.jsonl", entry)
        if self.log:
            what = entry.get("program") or f"vtcl[{entry.get('session')}]"
            line = (f"[{what} {entry.get('summary', '')[:120]}] exit {entry.get('exit')} "
                    f"{entry.get('seconds', 0):.1f}s")
            try:
                with self.log.open("a") as stream:
                    stream.write(line + "\n")
            except OSError:
                pass

    def run_program(self, payload: dict, out: Stream) -> None:
        program = payload.get("program")
        args = [str(item) for item in payload.get("args", [])]
        cwd = inside(payload.get("cwd"), self.conversion)
        if program not in PROGRAMS:
            return out.send(exit=2, out=f"unknown program: {program!r}\n")
        if cwd is None:
            return out.send(exit=2, out=f"run {program} from inside {self.conversion}\n")
        if program == "vivado" and "-mode" not in args:
            args = ["-mode", "batch", *args]  # there is no display for the GUI
        started = time.monotonic()
        with self.jobs:
            if out.closed.is_set():
                return
            process = subprocess.Popen(
                xilinx.command(shlex.join([program, *args]), cwd, [self.conversion]),
                cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
            stopper = threading.Thread(target=lambda: out.closed.wait() and process.poll() is None
                                       and kill_tree(process.pid), daemon=True)
            stopper.start()
            for line in process.stdout:
                out.send(out=line)
            code = process.wait()
        out.send(exit=code)
        self.note({"program": program, "args": args, "cwd": str(cwd), "exit": code,
                   "cancelled": out.closed.is_set(), "seconds": round(time.monotonic() - started, 1),
                   "summary": shlex.join(args)})

    def tcl(self, payload: dict, out: Stream) -> None:
        action = payload.get("action", "run")
        name = str(payload.get("session") or "main")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", name):
            return out.send(exit=2, out="session names use letters, digits, '_', '.', '-'\n")
        if action == "list":
            with self.lock:
                rows = [f"{n}\t{'busy' if s.busy.locked() else 'idle'}\tpid {s.process.pid}\n"
                        for n, s in self.sessions.items() if s.alive()]
            return out.send(exit=0, out="".join(rows) or "no Tcl sessions\n")
        if action == "stop":
            with self.lock:
                session = self.sessions.pop(name, None)
            if session:
                session.stop()
            return out.send(exit=0, out=f"stopped {name}\n" if session else f"no session {name}\n")
        cwd = inside(payload.get("cwd"), self.conversion)
        if cwd is None or "{" in str(cwd) or "}" in str(cwd):
            return out.send(exit=2, out=f"run vtcl from inside {self.conversion}\n")
        code = str(payload.get("code", ""))
        with self.lock:
            session = self.sessions.get(name)
            if session and not session.alive():
                del self.sessions[name]
                session = None
            if session is None:
                if len(self.sessions) >= MAX_TCL_SESSIONS:
                    return out.send(exit=2, out=f"{MAX_TCL_SESSIONS} Tcl sessions are open; "
                                    f"stop one with vtcl -s NAME --stop\n")
                session = self.sessions[name] = TclSession(name, self)
        started = time.monotonic()
        result = session.run(code, cwd, out)
        out.send(exit=result)
        first = next((line.strip() for line in code.splitlines() if line.strip()), "")
        self.note({"session": name, "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                   "cwd": str(cwd), "exit": result, "cancelled": out.closed.is_set(),
                   "seconds": round(time.monotonic() - started, 1), "summary": first})

    def shutdown(self) -> None:
        with self.lock:
            sessions, self.sessions = list(self.sessions.values()), {}
        for session in sessions:
            session.stop()
        shutil.rmtree(self.code_dir, ignore_errors=True)


class TclSession:
    """A `vivado -mode tcl` process that keeps its state between commands.

    Each command is sourced at global scope, so variables, open checkpoints and
    loaded simulations persist. The session's own log is vtcl_<name>.log,
    written by Vivado inside its jail."""
    def __init__(self, name: str, toolbox: Toolbox):
        self.name, self.toolbox = name, toolbox
        self.busy = threading.Lock()
        self.lines: queue.Queue[str | None] = queue.Queue()
        conversion = toolbox.conversion
        self.process = subprocess.Popen(
            xilinx.command(shlex.join(["exec", "vivado", "-mode", "tcl", "-nojournal", "-notrace",
                                       "-log", f"vtcl_{name}.log"]),
                           conversion, [conversion], [toolbox.code_dir]),
            cwd=conversion, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
            start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if self.alive():
            kill_tree(self.process.pid)

    def run(self, code: str, cwd: Path, out: Stream) -> int:
        """Run ``code``; stream its output; 0 on success, 1 on a Tcl error."""
        with self.busy:
            if not self.alive():
                out.send(out=f"Tcl session {self.name} has exited; the next vtcl starts a new one\n")
                return 70
            token = uuid.uuid4().hex
            script = self.toolbox.code_dir / f"{token}.tcl"
            script.write_text(code)
            done = f"@@VRP_DONE_{token}"
            # Hold a job slot only while Vivado is working on this command.
            with self.toolbox.jobs:
                # Errors print their stack; a non-empty result prints like the
                # interactive shell would. The marker carries the catch code.
                try:
                    self.process.stdin.write(
                        f"cd {{{cwd}}}; set ::vrp_rc [catch {{uplevel #0 [list source -notrace {{{script}}}]}} "
                        f"::vrp_res ::vrp_opt]; if {{$::vrp_rc == 1}} {{puts [dict get $::vrp_opt -errorinfo]}} "
                        f"elseif {{$::vrp_res ne {{}}}} {{puts $::vrp_res}}; puts \"{done} $::vrp_rc\"; flush stdout\n")
                    self.process.stdin.flush()
                except OSError:
                    out.send(out=f"Tcl session {self.name} exited\n")
                    return 70
                while True:
                    line = self.lines.get()
                    if line is None:
                        out.send(out=f"Tcl session {self.name} exited\n")
                        return 70
                    if line.startswith(done):
                        script.unlink(missing_ok=True)
                        return 1 if line.split()[-1] == "1" else 0
                    out.send(out=line)


def serve(socket_path: Path, project: Path, output: Path,
          log: Path | None = None, recorder=None, ready=None, toolbox: Toolbox | None = None) -> None:
    """Answer evaluation requests on ``socket_path`` until the process ends."""
    if toolbox is None:
        toolbox = Toolbox(output.parent, recorder.log if recorder else None)
    become_subreaper()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.listen(16)
    if ready:
        ready.set()
    # At most MAX_JOBS toolchain jobs at once, shared with direct Vivado
    # commands; more would starve each other of CPU and memory.
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
            if payload is not None and payload.get("tool") in ("exec", "tcl"):
                out = Stream(conn)
                try:
                    (toolbox.run_program if payload["tool"] == "exec" else toolbox.tcl)(payload, out)
                except Exception as error:
                    out.send(exit=1, out=f"evaluation service: {type(error).__name__}: {error}\n")
                return
            if payload is not None:
                with toolbox.jobs:
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
                            entry["error"] = first_error(reply["output"])
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


STREAM_CLIENT = '''#!/usr/bin/env python3
"""Run {name} on the host, jailed to this conversion, and stream its output."""
import json
import os
import socket
import sys

SOCKET = {socket!r}
NAME = {name!r}
VTCL_HELP = """usage: vtcl [-s NAME] 'TCL CODE' | -f FILE.tcl | < FILE.tcl
       vtcl [-s NAME] --stop        end a session (and whatever it is running)
       vtcl --list                  list open sessions
A persistent `vivado -mode tcl` session (default name: main). Variables, open
checkpoints and loaded xsim snapshots survive between calls. Each call runs in
the caller's directory; exit status is 1 when the Tcl code raised an error.
The session's full log is vtcl_NAME.log in the conversion root."""


def request():
    if NAME != "vtcl":
        return {{"tool": "exec", "program": NAME, "args": sys.argv[1:], "cwd": os.getcwd()}}
    args, payload = sys.argv[1:], {{"tool": "tcl", "cwd": os.getcwd()}}
    if args[:1] in (["-h"], ["--help"]):
        print(VTCL_HELP)
        raise SystemExit(0)
    if args[:1] == ["-s"] and len(args) > 1:
        payload["session"], args = args[1], args[2:]
    if args == ["--stop"] or args == ["--list"]:
        payload["action"] = args[0][2:]
    elif args[:1] == ["-f"] and len(args) == 2:
        payload["code"] = open(args[1]).read()
    elif args:
        payload["code"] = " ".join(args)
    elif not sys.stdin.isatty():
        payload["code"] = sys.stdin.read()
    else:
        print(VTCL_HELP, file=sys.stderr)
        raise SystemExit(2)
    return payload


payload = request()
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
code = 70
try:
    client.connect(SOCKET)
    client.sendall(json.dumps(payload).encode() + b"\\n")
    buffer = b""
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        buffer += chunk
        *lines, buffer = buffer.split(b"\\n")
        for line in lines:
            message = json.loads(line)
            if "out" in message:
                sys.stdout.write(message["out"])
                sys.stdout.flush()
            if "exit" in message:
                code = int(message["exit"])
except OSError as error:
    print(f"cannot reach the evaluation service: {{error}}", file=sys.stderr)
raise SystemExit(code)
'''


def install_clients(bin_dir: Path, socket_path: Path) -> None:
    """Write the stubs the sandboxed agent calls: sim, synth, the Xilinx
    programs and vtcl."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool in ALLOWED:
        stub = bin_dir / tool
        stub.write_text(CLIENT.format(socket=str(socket_path), tool=tool, guide=TOOL_GUIDE))
        stub.chmod(0o755)
    for name in (*PROGRAMS, "vtcl"):
        stub = bin_dir / name
        stub.write_text(STREAM_CLIENT.format(socket=str(socket_path), name=name))
        stub.chmod(0o755)
