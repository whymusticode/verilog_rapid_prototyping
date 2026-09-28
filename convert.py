#!/usr/bin/env python3
"""Use Qwen Code, Codex, or Whale to convert Python to SystemVerilog RTL."""

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
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import evald
import codex_run


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


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--model", required=True, metavar="HARNESS[:MODEL]",
                        help="qwen, codex, or whale, optionally followed by :model-id")
    source = parser.add_mutually_exclusive_group(required=True)
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
    parser.add_argument("--token-budget", type=float, default=150000,
                        help="per-project weighted Codex token limit (default: 150000; 0 disables)")
    parser.add_argument("--token-weights", type=float, nargs=3, default=[1, 5, 0.1],
                        metavar=("INPUT", "OUTPUT", "CACHED"),
                        help="weights for uncached input, output and cached input (default: 1 5 0.1)")
    parser.add_argument("--prompt-version", choices=("baseline", "v2"), default="baseline")
    parser.add_argument("--qwen", default=os.environ.get("QWEN", "qwen"),
                        help="Qwen executable (default: $QWEN or qwen)")
    parser.add_argument("--codex", default=os.environ.get("CODEX", "codex"),
                        help="Codex executable (default: $CODEX or codex)")
    parser.add_argument("--whale", default=os.environ.get("WHALE", "whale"),
                        help="Whale executable (default: $WHALE or whale)")
    parser.add_argument("--allow-write", type=Path, action="append", default=[],
                        metavar="PATH", help="additional writable sandbox path")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command and prompt without invoking the agent")
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


def prepare_layout(project: Path, conversion: Path) -> None:
    """Snapshot the reference once, before the agent or evaluators run."""
    copied = conversion / project.name
    alias = conversion / "python"
    if copied.is_symlink() or (copied.exists() and not copied.is_dir()):
        raise ValueError(f"reference copy is not a directory: {copied}")
    if project.name != "python" and (alias.exists() or alias.is_symlink()):
        if not alias.is_symlink() or alias.resolve() != copied:
            raise ValueError(f"python link already points elsewhere: {alias}")
    rtl = conversion / "rtl"
    if rtl.is_symlink() or (rtl.exists() and not rtl.is_dir()):
        raise ValueError(f"RTL path is not a directory: {rtl}")
    conversion.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project, copied, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    if project.name != "python" and not alias.is_symlink():
        alias.symlink_to(project.name, target_is_directory=True)
    rtl.mkdir(exist_ok=True)


def make_prompt(project: Path, output: Path, conversion: Path,
                extra: str = "", version: str = "baseline") -> str:
    copied = conversion / "python"
    params = copied / "params.yaml"
    extra_section = f"\nAdditional user requirements:\n{extra.strip()}\n" if extra.strip() else ""
    if version == "v2":
        return f"""Implement the numerical algorithm in python/main.py as synthesizable
SystemVerilog in rtl/. Your working/project root is {conversion}.
Read python/main.py and python/params.yaml, then build and evaluate the RTL.
You own this entire conversion folder, including the Python copy for debugging.
The original Python and parameters are checked independently after you finish;
changing the copy cannot change that final acceptance test.

The complete evaluator interface is documented in TOOL_GUIDE.md. Start there;
you do not need to discover the socket protocol or inspect evaluator internals.
`sim` and `synth` are ready-to-use commands on PATH, run from this directory.
There is no evald CLI to launch. Tools run synchronously; use a long shell yield
and wait for the existing process instead of launching duplicate evaluations.

Implementation contract:
- One top module; parameters WIDTH, FRAC, N, IN_LANES, OUT_LANES.
- Ports: input aclk, aresetn (active-low reset); input s_axis_tvalid,
  s_axis_tlast, [IN_LANES*WIDTH-1:0] s_axis_tdata; output s_axis_tready;
  output m_axis_tvalid, m_axis_tlast, [OUT_LANES*WIDTH-1:0] m_axis_tdata;
  input m_axis_tready. All transfers occur at posedge aclk when valid && ready.
- Lane 0 is the least-significant WIDTH bits. Each lane is signed two's
  complement with FRAC fractional bits. Complex samples pack real then imaginary.
- N is the frame size in params.yaml, not necessarily the algorithm's inner
  block size. TLAST must mark every Nth accepted output sample. Frames stream
  back to back. Reset algorithm state at the frame boundaries required by Python.
- Hold valid, data and last stable under output backpressure. Advance counters
  only on accepted transfers. Sustain N*target.frequency/target.cycles input
  samples per second; a design that blocks input throughout computation can
  violate the budget even when a single isolated frame works.
- Preserve numerical precision comparable to params.yaml bits. Precision is a
  continuous metric: 14 bits is better than 13, not equivalent because both
  clear a cutoff. Keep wide signed products and guard bits; round only when needed.
  FRAC is selected from observed input/output magnitudes and can vary between
  runs. Do not hard-code it or use random stimulus as constants.

Work loop:
1. Read the reference and parameters. Work out the arithmetic widths, sample
   order, frame boundaries and sustainable initiation interval before coding.
2. Implement a simple resource-conscious architecture and run `sim`.
   Use the reported worst errors and IO artifacts to fix numerical/handshake
   errors. First establish the intended computation (several meaningful bits,
   not nonsense outputs) and low cycles. There is no performance pass/fail.
3. Improve precision toward the params.yaml bit width and reduce cycles/resources.
   Run `synth` for resource counts and estimated Fmax. Compare raw measurements;
   zero exit status only means the measurement completed, not that it is good.
4. Make at least one measured architecture/precision/cycle/resource improvement
   if a bottleneck remains. Change one idea at a time and rerun sim then synth.
   Timing closure is normally LAST: once computation and cycles are sound, use
   `synth --paths 5` to locate critical paths and revise pipelining.
5. Finish with `sim --drain-stall 20` to test backpressure and `synth --implement`
   for routed Fmax. Report actual measurements, remaining failures and changed
   reference files. Report measured numbers, not a generic passing verdict.

Do not install software, commit, push, or change anything outside this conversion.
Use the supplied tools rather than trying to invoke Vivado inside the sandbox.
The runner records every evaluation and terminates at the weighted token budget.
{extra_section}"""
    return f"""Convert the Python numerical reference in {copied} into production-quality,
synthesizable SystemVerilog in {output}.

You are the implementation agent, not a consultant. Inspect {copied / 'main.py'} and
{params}, create the RTL, run the supplied evaluators, diagnose failures, and keep
editing and retesting to improve the measured implementation. Do not merely
describe code or stop after the first draft.

Hard boundaries (enforced by a sandbox; violations fail as I/O errors):
- Treat everything outside {conversion} as read-only. The original source at
  {project} is read-only; never edit evaluator scripts, repository files,
  configuration, or git state.
- You may inspect and edit the copied Python under {copied}, RTL under {output},
  and generated simulation artifacts under {conversion / 'IO'}.
- Do not commit, push, install software, or modify RTL_examples.

Required RTL contract:
- Synthesizable SystemVerilog (.sv or .v), with exactly one inferable top module.
- The top module must implement the AXI4-Stream interface expected by sim.py and
  accept parameters WIDTH, FRAC, N, IN_LANES, and OUT_LANES.
- Obey TVALID/TREADY backpressure, and assert TLAST on every Nth output beat:
  sim streams several N-beat frames back to back, so TLAST marks each frame
  boundary rather than the end of the stream. Implement the
  requested computation rather than special-casing any particular input; the
  stimulus is random and regenerated per run. Inspect generated IO files when
  they help debugging; do not hard-code their contents.
- Use fixed-point arithmetic appropriate for params.yaml and the Python oracle.

Evaluation loop (run these exact commands; they are on your PATH):
  sim
  synth

First establish the intended computation and low cycle count. Improve numerical
precision toward params.yaml bits and reduce FPGA resources and cycles. Timing
closure is normally the last optimization step. Compare actual numerical metrics,
not performance pass/fail thresholds. Prefer efficient pipelining, memories, and
DSP blocks over enormous combinational or fully unrolled structures. Re-run both
evaluators after meaningful changes; their printed metrics are the ground truth.
If an evaluator cannot obtain a measurement, use its error as feedback and continue.
The `sim` command tests against the Python copy in this conversion. After you
finish, the runner also checks the final RTL against the original source.

Finish only with a short report of the final simulation and synthesis metrics and
the files created or changed in {conversion}.{extra_section}"""

def qwen_command(args: argparse.Namespace, prompt: str) -> list[str]:
    command = [args.qwen, "-p", prompt, "--approval-mode", "yolo",
               "--output-format", "text",
               "--include-directories", str(args.input.resolve()),
               "--include-directories", str(ROOT)]
    model = args.model.partition(":")[2] or args.qwen_model
    if model:
        command.extend(("--model", model))
    return command


def codex_command(args: argparse.Namespace, prompt: str, conversion: Path) -> list[str]:
    command = [args.codex, "exec", "--dangerously-bypass-approvals-and-sandbox",
               "--skip-git-repo-check", "--ephemeral", "-C", str(conversion)]
    model = args.model.partition(":")[2]
    if model:
        command.extend(("--model", model))
    return [*command, prompt]


def whale_command(args: argparse.Namespace, prompt: str) -> list[str]:
    command = [args.whale, "exec", "--dangerously-skip-permissions"]
    model = args.model.partition(":")[2]
    if model:
        command.extend(("--model", model))
    return [*command, prompt]


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def whale_home() -> Path:
    return Path(os.environ.get("WHALE_HOME", Path.home() / ".whale")).expanduser().resolve()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def public_settings(value: object) -> object:
    """Keep configuration useful for comparisons without recording credentials."""
    if isinstance(value, dict):
        return {key: public_settings(item) for key, item in value.items()
                if isinstance(key, str) and not re.search(
                    r"key|token|secret|password|credential|authorization|auth", key,
                    re.IGNORECASE)}
    if isinstance(value, list):
        return [public_settings(item) for item in value]
    return value


def public_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if port:
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def cli_version(executable: str) -> str | None:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True,
                                text=True, timeout=5, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def codex_catalog(executable: str) -> tuple[dict, str]:
    try:
        result = subprocess.run([executable, "debug", "models"], capture_output=True,
                                text=True, timeout=10, check=True)
        catalog = json.loads(result.stdout)
        if isinstance(catalog, dict) and isinstance(catalog.get("models"), list):
            return catalog, "codex debug models"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError):
        pass
    cached = read_json(codex_home() / "models_cache.json")
    return cached, "Codex models_cache.json" if cached else "unavailable"


def model_info(args: argparse.Namespace, projects: list[Path]) -> dict:
    """Snapshot non-secret model and harness settings for a batch experiment."""
    harness, _, requested = args.model.partition(":")
    info = {"model": requested or None, "harness": harness}
    if harness == "codex":
        config = read_toml(codex_home() / "config.toml")
        active_config = dict(config)
        profiles = config.get("profiles")
        profile = config.get("profile")
        if isinstance(profiles, dict) and isinstance(profile, str):
            selected_profile = profiles.get(profile)
            if isinstance(selected_profile, dict):
                active_config.update(selected_profile)
        catalog, source = codex_catalog(args.codex)
        models = [item for item in catalog.get("models", [])
                  if isinstance(item, dict) and isinstance(item.get("slug"), str)]
        selected = requested or active_config.get("model")
        if not selected:
            visible = [item for item in models if item.get("visibility") == "list"]
            selected = min(visible, key=lambda item: item.get("priority", 9999)).get("slug") if visible else None
        info["model"] = selected
        info["cli_version"] = cli_version(args.codex)
        info["catalog_source"] = source
        for key in ("model_reasoning_effort", "model_verbosity", "service_tier",
                    "model_provider", "profile"):
            if isinstance(active_config.get(key), (str, int, float, bool)):
                info[f"configured_{key}"] = active_config[key]
        entry = next((item for item in models if item["slug"] == selected), None)
        if entry:
            # These are prompt/onboarding text, not adjustable model settings.
            excluded = {"slug", "base_instructions", "model_messages",
                        "availability_nux"}
            info.update((key, value) for key, value in entry.items()
                        if key not in excluded)
    elif harness == "qwen":
        config = read_json(Path.home() / ".qwen" / "settings.json")
        configured = config.get("model")
        info["model"] = requested or args.qwen_model or (
            configured.get("name") if isinstance(configured, dict) else None)
        info["cli_version"] = cli_version(args.qwen)
        if isinstance(configured, dict):
            info["configured_model_settings"] = public_settings(configured)
    else:
        config = read_toml(whale_home() / "config.toml")
        info["model"] = requested or config.get("model") or "deepseek-v4-flash"
        info["cli_version"] = cli_version(args.whale)
        for key in ("reasoning_effort", "thinking_enabled"):
            if key in config:
                info[key] = config[key]
        providers = config.get("providers")
        provider = providers.get("deepseek", {}) if isinstance(providers, dict) else {}
        if isinstance(provider, dict):
            for key in ("api", "web_search"):
                if key in provider:
                    info[key] = provider[key]
        if os.environ.get("WHALE_API"):
            info["api"] = os.environ["WHALE_API"]
        endpoint = config.get("api")
        base_url = os.environ.get("DEEPSEEK_BASE_URL") or (
            endpoint.get("base_url") if isinstance(endpoint, dict) else None)
        if url := public_url(base_url):
            info["api_base_url"] = url
    info["test_file"] = str(args.test)
    info["token_budget"] = args.token_budget
    info["token_weights"] = dict(zip(("uncached_input", "output", "cached_input"), args.token_weights))
    info["prompt_version"] = args.prompt_version
    info["codex_transport"] = "app-server" if harness == "codex" else None
    info["projects"] = [str(project) for project in projects]
    info["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    info["harness_sources_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("convert.py", "codex_run.py", "evald.py", *EVALUATORS)}
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
        elif index >= 2 and command[index - 2:index] == ["--setenv", "DEEPSEEK_API_KEY"]:
            shown.append("<REDACTED>")
        else:
            shown.append(part)
    return shlex.join(shown)


def complete_models(prefix: str) -> None:
    """Offer the visible models in Codex's /model catalog."""
    if prefix in ("", "qwen"):
        print("qwen")
    if "whale".startswith(prefix):
        print("whale")
    if not prefix.startswith("codex:") and "codex:".startswith(prefix):
        print("codex:")
    if not prefix.startswith("codex:"):
        return
    try:
        result = subprocess.run(
            [os.environ.get("CODEX", "codex"), "debug", "models"],
            capture_output=True, text=True, timeout=5, check=True)
        catalog = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError):
        try:
            catalog = json.loads((codex_home() / "models_cache.json").read_text())
        except (OSError, ValueError):
            return
    for model in catalog.get("models", []):
        if isinstance(model, dict) and model.get("visibility") == "list":
            slug = model.get("slug")
            if isinstance(slug, str) and f"codex:{slug}".startswith(prefix):
                print(f"codex:{slug}")


def workspace(conversion: Path) -> list[Path]:
    """The conversion directory is the agent's writable workspace."""
    return [conversion]


def sandbox_command(command: list[str], project: Path, conversion: Path,
                    writable: list[Path], service: Path, stubs: Path,
                    extra_write: list[Path], harness: str) -> list[str]:
    """Hide the host: a minimal environment, reads limited to the input project,
    writes limited to the conversion directory, and evaluators reachable as
    two stub commands that talk to the service on ``service``."""
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
    if harness == "qwen" and (home / ".qwen").exists():
        wrapped.extend(("--bind", str(home / ".qwen"), str(home / ".qwen")))
    if harness == "codex":
        auth = codex_home()
        if not auth.is_dir():
            raise RuntimeError(f"Codex home does not exist: {auth}")
        wrapped.extend(("--bind", str(auth), str(auth)))
        wrapped.extend(("--setenv", "CODEX_HOME", str(auth)))
    if harness == "whale":
        state = whale_home()
        if not state.is_dir():
            raise RuntimeError(f"Whale home does not exist: {state}; run whale setup first")
        wrapped.extend(("--bind", str(state), str(state)))
        wrapped.extend(("--setenv", "WHALE_HOME", str(state)))
        for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "WHALE_API"):
            if value := os.environ.get(name):
                wrapped.extend(("--setenv", name, value))

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


def check_references(project: Path, output: Path, conversion: Path, recorder=None) -> None:
    """Check finished RTL against fresh samples from both reference versions."""
    changed = reference_changes(project, conversion)
    results = []
    for label, reference in (("copied", None), ("original", project)):
        if recorder:
            reply = recorder.evaluate("sim", [], label)
            status, printed = reply["exit"], reply["output"]
        else:
            extra = [] if reference is None else [str(reference)]
            extra.extend(("--io", str(conversion / "final_checks" / label)))
            status, printed = evald.evaluate("sim", extra, output)
        results.append((label, status, printed))

    report = conversion / "reference_check.log"
    try:
        fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                     0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("Changed Python/parameter files: "
                         + (", ".join(changed) if changed else "none") + "\n")
            for label, status, printed in results:
                stream.write(f"\n=== {label} reference (exit {status}) ===\n{printed}")
    except OSError as error:
        raise RuntimeError(f"cannot write reference check: {error}") from error

    print(f"changed reference files: {', '.join(changed) if changed else 'none'}")
    for label, status, printed in results:
        metrics = evald.measurements(printed)
        print(f"final {label} simulation: {'completed' if status == 0 else 'failed'}"
              f" {metrics}; details: {report}")
    if any(status for _, status, _ in results):
        raise RuntimeError(f"final reference check failed; see {report}")


def run_one(args: argparse.Namespace, harness: str) -> int:
    project, output, conversion = validate(args)
    prompt = make_prompt(project, output, conversion, args.extra_prompt, args.prompt_version)
    writable = workspace(conversion)
    with tempfile.TemporaryDirectory(prefix="vrp-service-") as runtime_name:
        runtime = Path(runtime_name)
        service, stubs = runtime / "run", runtime / "bin"
        service.mkdir()
        evald.install_clients(stubs, service / "evald.sock")
        agent_command = (qwen_command(args, prompt) if harness == "qwen" else
                         [args.codex, "app-server"] if harness == "codex" else
                         whale_command(args, prompt))
        command = sandbox_command(agent_command, project, conversion, writable,
                                  service, stubs, args.allow_write, harness)
        if args.dry_run:
            print(f"reference copy: {conversion / project.name}")
            print(f"python link: {conversion / 'python'}")
            print("command:", display_command(command, prompt))
            print("\nprompt:\n" + prompt)
            return 0

        prepare_layout(project, conversion)
        if args.prompt_version == "v2":
            (conversion / "TOOL_GUIDE.md").write_text(evald.TOOL_GUIDE)
        (conversion / "prompt.txt").write_text(prompt)
        usage = codex_run.Usage(args.token_budget, args.token_weights)
        recorder = evald.Recorder(project, output, usage if harness == "codex" else None)
        ready = threading.Event()
        # The service owns the toolchain and outlives nothing: it is a daemon
        # thread, so it goes away with this process however the run ends.
        threading.Thread(target=evald.serve,
                         args=(service / "evald.sock", project, output,
                               conversion / "evald.jsonl", recorder, ready),
                         daemon=True).start()
        if not ready.wait(5):
            raise RuntimeError("evaluation service did not start")
        log = conversion / "convert.log"
        print(f"running {harness} in {conversion}")
        print(f"log: {log}")
        if harness == "codex":
            returncode, result = codex_run.run(command, conversion, prompt,
                                             args.model.partition(":")[2], usage, terminate, log)
            print(f"agent stopped: {result['status']}; weighted tokens: {result['weighted_tokens']}")
        else:
            with log.open("w") as stream:
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
        details = model_info(args, projects)
        batch.mkdir(parents=True, exist_ok=True)
        write_model_info(batch, details)
        source_archive = batch / "harness_sources"
        source_archive.mkdir()
        for name in details["harness_sources_sha256"]:
            shutil.copy2(ROOT / name, source_archive / name)
        print(f"model settings: {batch / 'model_info.yaml'}", flush=True)
    failures = []
    for index, (project, output) in enumerate(items, 1):
        print(f"[{index}/{len(items)}] {project} -> {output}", flush=True)
        runner = ROOT / "convert.py" if args.dry_run else source_archive / "convert.py"
        command = [sys.executable, str(runner), "-m", args.model,
                   "-i", str(project), "-o", str(output),
                   "--qwen", args.qwen, "--codex", args.codex,
                   "--whale", args.whale]
        command.extend(("--token-budget", str(args.token_budget), "--token-weights",
                        *map(str, args.token_weights), "--prompt-version", args.prompt_version))
        if args.qwen_model:
            command.extend(("--qwen-model", args.qwen_model))
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
        complete_models(argv[1])
        return 0
    args = arguments(argv)
    import math
    if any(not math.isfinite(v) or v < 0 for v in [args.token_budget, *args.token_weights]) or not any(args.token_weights):
        raise ValueError("token budget and weights must be finite and nonnegative, with a positive weight")
    harness, separator, model = args.model.partition(":")
    if harness not in ("qwen", "codex", "whale") or (separator and not model):
        raise ValueError("-m must be qwen, codex, whale, or HARNESS:MODEL")
    if args.qwen_model and (harness != "qwen" or separator):
        raise ValueError("--qwen-model requires -m qwen without a model suffix")
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
