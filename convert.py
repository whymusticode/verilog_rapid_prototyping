#!/usr/bin/env python3
"""Use Qwen Code, Codex, Claude Code, or Whale to convert Python to SystemVerilog RTL."""

from __future__ import annotations

import argparse
import filecmp
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jinja2

import claude_run
import codex_run
import evald
import model


ROOT = Path(__file__).resolve().parent

# The evaluators are readable so the agent can learn the interface contract.
# They run outside the sandbox, but place simulation artifacts in conversion/IO.
EVALUATORS = ("sim.py", "synth.py", "vrp.py")

# Read-only system paths the sandboxed agent needs. The FPGA toolchain is not
# among them: evald.py runs the evaluators out here and the agent reaches them
# through a socket, so Vivado and Nix stay outside entirely.
SYSTEM_READ = ("/nix/store", "/run/current-system", "/bin", "/usr",
               "/etc/passwd", "/etc/group", "/etc/hosts", "/etc/resolv.conf",
               "/etc/nsswitch.conf", "/etc/localtime", "/etc/ssl",
               "/etc/static", "/etc/pki")
SANDBOX_PATH = "/run/current-system/sw/bin"
# Harness sources archived with a batch; its runs execute the archived convert.py.
SOURCES = ("convert.py", "model.py", "codex_run.py", "claude_run.py", "evald.py", "xilinx.py",
           "prompts/convert.md.j2", "prompts/tool_guide.md", *EVALUATORS)
# Written into each conversion before the agent starts; `--resume DIR` reads it.
SESSION = "session.json"
RESUMABLE = ("codex", "claude")
# Per-run records moved aside when a session is resumed, so each run keeps its own.
RUN_RECORDS = ("run.json", "agent_events.jsonl", "tokens.jsonl", "convert.log",
               "reference_check.log")
RESUME_PROMPT = ("Your previous run in this directory ended ({status}). Continue the "
                 "conversion from where you left off; the files are as you left them.")
RETARGET_PROMPT = ("Your previous run in this directory ended ({status}). The reference has "
                   "changed: python/ now links to {name}/, a fresh copy of {project}, and the "
                   "final check measures your RTL against it. The previous reference copy is "
                   "still at {previous}/. Your RTL, PLAN.md and other files are as you left "
                   "them. Re-read python/main.py, python/params.yaml and TOOL_GUIDE.md, update "
                   "PLAN.md for the new reference, then adapt and extend your existing design "
                   "to it, reusing what still applies.")


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--model", metavar="HARNESS[:MODEL]",
                        help="qwen, codex, claude, or whale, optionally followed by :model-id "
                             "(required unless resuming a session)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("-i", "--input", type=Path,
                        help="project containing main.py and params.yaml")
    source.add_argument("-t", "--test", type=Path, metavar="FILE",
                        help="file listing projects to convert, one path per line")
    parser.add_argument("-o", "--output", type=Path,
                        help="conversion directory, or batch parent with -t "
                             "(default: next numbered directory)")
    parser.add_argument("--qwen-model", metavar="MODEL",
                        help="Qwen model ID or alias (default: Qwen CLI configuration)")
    parser.add_argument("--extra-prompt", default="", metavar="TEXT",
                        help="additional conversion requirements")
    parser.add_argument("--token-budget", type=float, default=1000000,
                        help="per-project weighted Codex/Claude token limit (default: 1000000; 0 disables)")
    parser.add_argument("--token-weights", type=float, nargs=3, default=[1, 5, 0.1],
                        metavar=("INPUT", "OUTPUT", "CACHED"),
                        help="weights for uncached input, output and cached input (default: 1 5 0.1)")
    parser.add_argument("--reasoning-effort", choices=("none", "minimal", "low", "medium", "high", "xhigh", "max"),
                        help="Codex or Claude reasoning effort; omitted uses the harness configuration")
    parser.add_argument("--qwen", default=os.environ.get("QWEN", "qwen"),
                        help="Qwen executable (default: $QWEN or qwen)")
    parser.add_argument("--codex", default=os.environ.get("CODEX", "codex"),
                        help="Codex executable (default: $CODEX or codex)")
    parser.add_argument("--claude", default=os.environ.get("CLAUDE", "claude"),
                        help="Claude Code executable (default: $CLAUDE or claude)")
    parser.add_argument("--whale", default=os.environ.get("WHALE", "whale"),
                        help="Whale executable (default: $WHALE or whale)")
    parser.add_argument("--resume", type=Path, metavar="DIR",
                        help=f"a conversion directory with {SESSION}: continue its Codex/Claude "
                             "session in place")
    parser.add_argument("--allow-write", type=Path, action="append", default=[],
                        metavar="PATH", help="additional writable sandbox path")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command and prompt without invoking the agent")
    parser.set_defaults(session=None, retarget_from=None)
    return parser.parse_args(argv)


def next_output(parent: Path, prefix: str) -> Path:
    pattern = re.compile(rf"{re.escape(prefix)}_(\d+)$")
    numbers = [int(match.group(1)) for path in parent.iterdir()
               if (match := pattern.fullmatch(path.name))]
    return parent / f"{prefix}_{max(numbers, default=-1) + 1:03d}"


def test_projects(test_file: Path) -> list[Path]:
    source = test_file.resolve()
    if not source.is_file():
        raise ValueError(f"test file does not exist: {test_file}")
    projects = []
    for line in source.read_text().splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#"):
            path = Path(entry).expanduser()
            projects.append((path if path.is_absolute() else source.parent / path).resolve())
    if not projects:
        raise ValueError(f"test file contains no projects: {test_file}")
    return projects


def validate(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    project = args.input.resolve()
    conversion = args.output.resolve()
    output = conversion / "rtl"
    if not project.is_dir():
        raise ValueError(f"input project does not exist: {args.input}")
    for required in ("main.py", "params.yaml"):
        if not (project / required).is_file():
            raise ValueError(f"input project is missing {required}: {project}")
    if conversion == project or project in conversion.parents or conversion in project.parents:
        raise ValueError("input and output directories must not contain one another")
    if conversion == Path(conversion.anchor) or conversion == Path.home():
        raise ValueError(f"output directory is too shallow to sandbox: {conversion}")
    if project.name in {"rtl", "IO"}:
        raise ValueError(f"input project name conflicts with conversion layout: {project.name}")
    return project, output, conversion


def prepare_layout(project: Path, conversion: Path, retarget: bool = False) -> None:
    """Snapshot the reference once, before the agent or evaluators run.

    ``retarget`` moves an existing conversion's python link to a new reference."""
    copied = conversion / project.name
    alias = conversion / "python"
    if copied.is_symlink() or (copied.exists() and not copied.is_dir()):
        raise ValueError(f"reference copy is not a directory: {copied}")
    if project.name != "python" and (alias.exists() or alias.is_symlink()):
        if not alias.is_symlink() or (alias.resolve() != copied and not retarget):
            raise ValueError(f"python link already points elsewhere: {alias}")
    rtl = conversion / "rtl"
    if rtl.is_symlink() or (rtl.exists() and not rtl.is_dir()):
        raise ValueError(f"RTL path is not a directory: {rtl}")
    conversion.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project, copied, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    if project.name != "python" and alias.is_symlink() and alias.resolve() != copied:
        alias.unlink()
    if project.name != "python" and not alias.is_symlink():
        alias.symlink_to(project.name, target_is_directory=True)
    rtl.mkdir(exist_ok=True)


def load_session(args: argparse.Namespace) -> None:
    """Point the arguments at the conversion and agent session ``--resume`` names."""
    if not (args.resume / SESSION).is_file():
        raise ValueError(f"--resume needs a conversion directory with {SESSION}: {args.resume}")
    saved = json.loads((args.resume / SESSION).read_text())
    if args.test:
        raise ValueError("resuming a session continues one conversion; it cannot be combined with -t")
    if not saved.get("session_id"):
        raise ValueError(f"{args.resume / SESSION} records no session id; the agent never started")
    conversion = args.resume.resolve()
    if args.output and args.output.resolve() != conversion:
        raise ValueError("a resumed session continues in its own directory; omit -o")
    # A different -i retargets the session: the agent keeps its work and memory
    # but continues against the new reference.
    project = args.input.resolve() if args.input else Path(saved["input"])
    args.retarget_from = Path(saved["input"]) if project != Path(saved["input"]) else None
    args.model = args.model or saved["model"]
    if args.model.partition(":")[0] != saved["harness"]:
        raise ValueError(f"session {saved['session_id']} belongs to {saved['harness']}, not {args.model}")
    if args.reasoning_effort is None:
        args.reasoning_effort = saved.get("reasoning_effort")
    args.input, args.output, args.session = project, conversion, saved


def read_run(conversion: Path) -> dict:
    try:
        return json.loads((conversion / "run.json").read_text())
    except (OSError, ValueError):
        return {}


def save_session(conversion: Path, record: dict) -> None:
    (conversion / SESSION).write_text(json.dumps(record, indent=2) + "\n")


def archive_run(conversion: Path) -> Path:
    """Move the stopped run's records aside before the resumed run writes its own."""
    parent = conversion / "previous_runs"
    parent.mkdir(exist_ok=True)
    target = parent / f"{len(list(parent.iterdir())) + 1:02d}"
    target.mkdir()
    for name in RUN_RECORDS:
        if (conversion / name).is_file():
            shutil.move(conversion / name, target / name)
    return target


def make_prompt(project: Path, conversion: Path, extra: str = "") -> str:
    """Render prompts/convert.md.j2 for one conversion."""
    environment = jinja2.Environment(loader=jinja2.FileSystemLoader(ROOT / "prompts"),
                                     undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    return environment.get_template("convert.md.j2").render(
        project=project, conversion=conversion, extra=extra.strip())


def batch_info(args: argparse.Namespace, projects: list[Path]) -> dict:
    """Model settings plus everything else that defines a batch experiment."""
    info = model.settings(args)
    info["test_file"] = str(args.test)
    info["token_budget"] = args.token_budget
    info["token_weights"] = dict(zip(("uncached_input", "output", "cached_input"), args.token_weights))
    info["projects"] = [str(project) for project in projects]
    info["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    info["harness_sources_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    return info


def write_model_info(batch: Path, info: dict) -> None:
    """JSON flow values are valid YAML and need no extra package dependency."""
    path = batch / "model_info.yaml"
    content = "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
                      for key, value in info.items())
    with path.open("x") as stream:
        stream.write(content)


def display_command(command: list[str], prompt: str) -> str:
    """Show a dry run without exposing a forwarded API key."""
    shown = []
    for index, part in enumerate(command):
        if part == prompt:
            shown.append("<PROMPT>")
        elif index >= 2 and command[index - 2] == "--setenv" and command[index - 1] in model.SECRET_ENV:
            shown.append("<REDACTED>")
        else:
            shown.append(part)
    return shlex.join(shown)


def workspace(conversion: Path) -> list[Path]:
    """The conversion directory is the agent's writable workspace."""
    return [conversion]


def sandbox_command(command: list[str], project: Path, conversion: Path,
                    writable: list[Path], service: Path, stubs: Path,
                    extra_write: list[Path], harness: str) -> list[str]:
    """Hide the host: a minimal environment, reads limited to the input project,
    writes limited to the conversion directory, and the evaluators and Xilinx
    tools reachable as stub commands that talk to the service on ``service``."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bubblewrap (bwrap) is required to run the agent safely")
    home = Path.home()
    user = getpass.getuser()
    wrapped = [bwrap, "--die-with-parent", "--unshare-pid", "--unshare-ipc",
               "--unshare-uts", "--new-session",
               # Start from an empty environment so nothing in the caller's
               # shell - API keys, tokens, proxies - reaches the agent. The
               # network namespace is shared so the CLI can reach its model.
               "--clearenv",
               "--setenv", "HOME", str(home),
               "--setenv", "USER", user,
               "--setenv", "LOGNAME", user,
               "--setenv", "PATH", f"{stubs}:{SANDBOX_PATH}",
               "--setenv", "TMPDIR", "/tmp",
               "--setenv", "LANG", "C.UTF-8",
               "--setenv", "TERM", "dumb",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]

    reads = [Path(path) for path in SYSTEM_READ]
    reads.extend((project, stubs))
    reads.extend(ROOT / name for name in EVALUATORS)
    for path in dict.fromkeys(reads):
        if path.exists():
            wrapped.extend(("--ro-bind", str(path), str(path)))

    # Read-write mounts come last so they win over any read-only parent. The
    # service directory holds only the socket; connecting to it needs write.
    for path in [*writable, service, *(path.resolve() for path in extra_write)]:
        wrapped.extend(("--bind", str(path), str(path)))
    wrapped.extend(model.sandbox_binds(harness))

    # Everything above was mounted onto a fresh tmpfs root; sealing it stops
    # stray writes from landing in a scratch skeleton that silently disappears.
    # Child mounts keep their own flags, so the binds above are unaffected.
    wrapped.extend(("--remount-ro", "/"))
    wrapped.extend(("--chdir", str(conversion)))
    return [*wrapped, "--", *command]


def terminate(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def reference_changes(project: Path, conversion: Path) -> list[str]:
    """Report edits to the copied Python and parameter files."""
    copied = conversion / "python"
    if conversion not in copied.resolve().parents:
        raise RuntimeError(f"python link no longer points inside {conversion}: {copied}")

    def files(root: Path) -> set[Path]:
        return {path.relative_to(root) for path in root.rglob("*")
                if path.suffix in {".py", ".yaml", ".yml"}
                and "__pycache__" not in path.parts}

    changed = []
    for relative in sorted(files(project) | files(copied)):
        original, current = project / relative, copied / relative
        if (not original.is_file() or not current.is_file()
                or original.is_symlink() or current.is_symlink()
                or not filecmp.cmp(original, current, shallow=False)):
            changed.append(str(relative))
    return changed


def check_references(project: Path, output: Path, conversion: Path, recorder) -> None:
    """Measure finished RTL against the original project, not the agent's copy.

    The agent can edit anything in its workspace (the copied Python, params and
    IO/), so the closing simulation uses the original reference. It regenerates
    IO/tb.sv, which the implementation run (with the original params) elaborates.
    """
    changed = reference_changes(project, conversion)
    results = []
    sim = recorder.evaluate("sim", [], "original")
    results.append(("original simulation", sim["exit"], sim["output"]))
    synth = recorder.evaluate("synth", ["--implement"], "original")
    results.append(("original implementation", synth["exit"], synth["output"]))

    report = conversion / "reference_check.log"
    try:
        fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                     0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("Changed Python/parameter files: "
                         + (", ".join(changed) if changed else "none") + "\n")
            for label, status, printed in results:
                stream.write(f"\n=== {label} (exit {status}) ===\n{printed}")
    except OSError as error:
        raise RuntimeError(f"cannot write reference check: {error}") from error

    print(f"changed reference files: {', '.join(changed) if changed else 'none'}")
    for label, status, printed in results:
        metrics = evald.measurements(printed)
        print(f"final {label}: {'completed' if status == 0 else 'failed'}"
              f" {metrics}; details: {report}")
    if any(status for _, status, _ in results):
        raise RuntimeError(f"final reference check failed; see {report}")


def run_one(args: argparse.Namespace, harness: str) -> int:
    project, output, conversion = validate(args)
    session = args.session
    if session:
        previous = read_run(conversion)
        status = previous.get("status", "unknown reason")
        if args.retarget_from:
            prompt = RETARGET_PROMPT.format(status=status, name=project.name, project=project,
                                            previous=args.retarget_from.name)
        else:
            prompt = RESUME_PROMPT.format(status=status)
        if args.extra_prompt.strip():
            prompt += "\n\n" + args.extra_prompt.strip()
    else:
        prompt = make_prompt(project, conversion, args.extra_prompt)
        # Claude takes its session id from us; Codex assigns its thread id on start.
        session = {"harness": harness, "model": args.model, "input": str(project),
                   "reasoning_effort": args.reasoning_effort,
                   "session_id": str(uuid.uuid4()) if harness == "claude" else None,
                   "created_utc": datetime.now(timezone.utc).isoformat(), "resumes": []}
    resuming = bool(args.session)
    writable = workspace(conversion)
    with tempfile.TemporaryDirectory(prefix="vrp-service-") as runtime_name:
        runtime = Path(runtime_name)
        service, stubs = runtime / "run", runtime / "bin"
        service.mkdir()
        evald.install_clients(stubs, service / "evald.sock")
        agent_command = model.command(args, harness, prompt, session["session_id"], resuming)
        command = sandbox_command(agent_command, project, conversion, writable,
                                  service, stubs, args.allow_write, harness)
        if args.dry_run:
            print(f"reference copy: {conversion / project.name}")
            print(f"python link: {conversion / 'python'}")
            print("command:", display_command(command, prompt))
            print("\nprompt:\n" + prompt)
            return 0

        if resuming:
            archived = archive_run(conversion)
            session["resumes"].append({"started_utc": datetime.now(timezone.utc).isoformat(),
                                       "previous_run": str(archived.relative_to(conversion))})
            if args.retarget_from:
                prepare_layout(project, conversion, retarget=True)
                session["resumes"][-1]["retargeted_from"] = session["input"]
                session["input"] = str(project)
                print(f"retargeted {conversion} from {args.retarget_from} to {project}")
            print(f"resuming {harness} session {session['session_id']}; previous run: {archived}")
        else:
            prepare_layout(project, conversion)
        if harness in RESUMABLE:
            save_session(conversion, session)
        (conversion / "TOOL_GUIDE.md").write_text(evald.TOOL_GUIDE)
        usage = codex_run.Usage(args.token_budget, args.token_weights)
        log = conversion / "convert.log"
        log.write_text("")
        recorder = evald.Recorder(project, output, usage if harness in ("codex", "claude") else None, log)
        toolbox = evald.Toolbox(conversion, log)
        ready = threading.Event()
        # The service owns the toolchain and outlives nothing: it is a daemon
        # thread, so it goes away with this process however the run ends.
        threading.Thread(target=evald.serve,
                         args=(service / "evald.sock", project, output,
                               conversion / "evald.jsonl", recorder, ready, toolbox),
                         daemon=True).start()
        if not ready.wait(5):
            raise RuntimeError("evaluation service did not start")
        print(f"running {harness} in {conversion}")
        print(f"log: {log}")
        if harness == "codex":
            def on_thread(thread_id):
                session["session_id"] = thread_id
                save_session(conversion, session)
            returncode, result = codex_run.run(command, conversion, prompt,
                                             args.model.partition(":")[2], usage, terminate, log,
                                             reasoning_effort=args.reasoning_effort,
                                             resume_thread=session["session_id"] if resuming else None,
                                             on_thread=on_thread)
            print(f"agent stopped: {result['status']}; weighted tokens: {result['weighted_tokens']}")
        elif harness == "claude":
            try:
                returncode, result = claude_run.run(command, conversion, prompt, usage, terminate, log,
                                                    reasoning_effort=args.reasoning_effort)
            except KeyboardInterrupt:
                raise RuntimeError(f"{harness} was interrupted; see {log}")
            print(f"agent stopped: {result['status']}; weighted tokens: {result['weighted_tokens']}")
        else:
            with log.open("a") as stream:
                try:
                    process = subprocess.Popen(command, cwd=conversion, text=True,
                                               stdin=subprocess.DEVNULL,
                                               stdout=stream, stderr=subprocess.STDOUT,
                                               start_new_session=True)
                except OSError as error:
                    raise RuntimeError(f"cannot start {harness}: {error}") from error
                try:
                    returncode = process.wait()
                except KeyboardInterrupt:
                    terminate(process)
                    raise RuntimeError(f"{harness} was interrupted; see {log}")
        # The agent is gone; its Tcl sessions would only hold memory.
        toolbox.shutdown()
        # Even a budget-exhausted or failed agent leaves an independently checked result.
        check_error = None
        try:
            check_references(project, output, conversion, recorder)
        except RuntimeError as error:
            check_error = error
        if returncode:
            tail = log.read_text(errors="replace").splitlines()[-40:]
            if tail:
                print("\n".join(tail), file=sys.stderr)
            if harness in RESUMABLE:
                print(f"continue with: python convert.py --resume {conversion}", file=sys.stderr)
            raise RuntimeError(f"{harness} exited with status {returncode}; see {log}")
        if check_error:
            raise check_error
        print(f"conversion complete: {output}")
        return 0


def run_batch(args: argparse.Namespace) -> int:
    projects = test_projects(args.test)
    batch = (args.output or next_output(Path.cwd(), "conversion_test")).resolve()
    items = [(project, batch / f"conversion_{index:03d}")
             for index, project in enumerate(projects)]
    for project, output in items:
        validate(argparse.Namespace(input=project, output=output))
    if not args.dry_run:
        if batch.exists() and not batch.is_dir():
            raise ValueError(f"batch output is not a directory: {batch}")
        if batch.exists() and any(batch.iterdir()):
            raise ValueError(f"batch directory is not empty: {batch}")
        details = batch_info(args, projects)
        batch.mkdir(parents=True, exist_ok=True)
        write_model_info(batch, details)
        source_archive = batch / "harness_sources"
        source_archive.mkdir()
        for name in details["harness_sources_sha256"]:
            (source_archive / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, source_archive / name)
        print(f"model settings: {batch / 'model_info.yaml'}", flush=True)
    failures = []
    for index, (project, output) in enumerate(items, 1):
        print(f"[{index}/{len(items)}] {project} -> {output}", flush=True)
        runner = ROOT / "convert.py" if args.dry_run else source_archive / "convert.py"
        command = [sys.executable, str(runner), "-m", args.model,
                   "-i", str(project), "-o", str(output),
                   "--qwen", args.qwen, "--codex", args.codex,
                   "--claude", args.claude, "--whale", args.whale]
        command.extend(("--token-budget", str(args.token_budget), "--token-weights",
                        *map(str, args.token_weights)))
        if args.qwen_model:
            command.extend(("--qwen-model", args.qwen_model))
        if args.reasoning_effort is not None:
            command.extend(("--reasoning-effort", args.reasoning_effort))
        if args.extra_prompt:
            command.extend(("--extra-prompt", args.extra_prompt))
        for path in args.allow_write:
            command.extend(("--allow-write", str(path)))
        if args.dry_run:
            command.append("--dry-run")
        if subprocess.run(command, check=False).returncode:
            failures.append(project.name)
    state = "batch dry run" if args.dry_run else "batch complete"
    print(f"{state}: {len(items) - len(failures)}/{len(items)} succeeded; {batch}")
    if failures:
        print(f"failed: {', '.join(failures)}", file=sys.stderr)
    return 1 if failures else 0


def run(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) == 2 and argv[0] == "--complete-models":
        model.complete_models(argv[1])
        return 0
    args = arguments(argv)
    if args.resume:
        load_session(args)
    elif args.model is None or (args.input is None and args.test is None):
        raise ValueError("-m and one of -i/-t are required unless --resume names a "
                         f"conversion directory with {SESSION}")
    import math
    if any(not math.isfinite(v) or v < 0 for v in [args.token_budget, *args.token_weights]) or not any(args.token_weights):
        raise ValueError("token budget and weights must be finite and nonnegative, with a positive weight")
    harness = model.check(args)
    if args.test:
        return run_batch(args)
    if args.output is None:
        args.output = next_output(Path.cwd(), "conversion")
    return run_one(args, harness)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (ValueError, RuntimeError) as error:
        print(f"convert.py: {error}", file=sys.stderr)
        raise SystemExit(1)
