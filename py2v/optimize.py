"""HLS optimization loop — iterates LLM tool calls to minimize clock_cycles.

Usage:
  python py2v/optimize.py <conversion_dir> [--max-rounds N]

Each round: show LLM the current summary + HLS files, it emits tool calls
(backup_file, write_file, read_file, write_plan, done), harness executes them,
runs C-sim, appends to summary.json, feeds results back.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from py2v.client import Client, cached, text
from py2v.util import compare, git_hash, next_version

OPTIMIZE_PROMPT = (Path(__file__).parent / "prompts" / "optimize.md").read_text()

TOOL_RE = re.compile(
    r"TOOL: (\w+)\n"
    r"(?:PATH: ([^\n]+)\n)?"
    r"(?:<<<\n(.*?)>>>)?",
    re.S,
)


def _strip_fences(s):
    return re.sub(r"^```[^\n]*\n|```$", "", s.strip(), flags=re.M).strip()


def _run_csim(conv, build, params):
    part = params["part"]
    clk_hz = float(params.get("clock", {}).get("freq_hz", 200e6))
    period_ns = 1000.0 / (clk_hz / 1e6)
    sim = build / "sim"
    sim.mkdir(parents=True, exist_ok=True)

    py_script = f"""\
import vitis, os, shutil
conv = {str(conv)!r}
build = {str(build)!r}
c = vitis.create_client()
c.update_workspace(conv)
c.set_workspace(conv)
comp_dir = os.path.join(conv, 'csim_prj')
if os.path.isdir(comp_dir):
    shutil.rmtree(comp_dir)
comp = c.create_hls_component(name='csim_prj')
cfg = c.get_config_file(os.path.join(conv, 'csim_prj', 'hls_config.cfg'))
cfg.set_value('', key='part', value={part!r})
cfg.add_lines('hls', ['syn.file=' + os.path.join(build, 'hls', 'kernel.cpp')])
cfg.add_lines('hls', ['tb.file=' + os.path.join(build, 'hls', 'tb.cpp')])
cfg.add_lines('hls', ['syn.top=kernel_top'])
cfg.add_lines('hls', ['clock={period_ns:.3f}'])
os.makedirs(os.path.join(build, 'sim'), exist_ok=True)
comp.run('C_SIMULATION')
vitis.dispose()
"""
    (build / "run_csim.py").write_text(py_script)
    env = os.environ.copy()
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    hls_bin = env.get("VITIS_HLS_BIN", "vitis")
    proc = subprocess.run(
        [hls_bin, "-s", str(build / "run_csim.py")],
        cwd=str(conv),
        env=env,
        capture_output=True,
        text=True,
    )
    (build / "csim.log").write_text((proc.stdout or "") + (proc.stderr or ""))
    return proc.returncode


def _read_summary(build, io_dir, manifest, params):
    sim = build / "sim"
    cmp = compare(io_dir, sim, manifest, params=params)
    clock_cycles_path = sim / "clock_cycles.txt"
    clock_cycles = int(clock_cycles_path.read_text().strip()) if clock_cycles_path.exists() else None
    return {"tensors": cmp, "clock_cycles": clock_cycles}


def _append_summary(build, summary, conv):
    summary["git"] = git_hash(conv)
    history_path = build / "summary.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    if not isinstance(history, list):
        history = [history]
    history.append(summary)
    history_path.write_text(json.dumps(history, indent=2))


def _hls_contents(build):
    result = {}
    for fname in ["kernel.h", "kernel.cpp", "tb.cpp"]:
        p = build / "hls" / fname
        if p.exists():
            result[fname] = p.read_text()
    return result


def _next_backup_ver(build):
    """Return next NNN for kernel_NNN.cpp backups."""
    existing = list((build / "hls").glob("kernel_[0-9]*.cpp"))
    indices = []
    for p in existing:
        try:
            indices.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return max(indices, default=-1) + 1


def _apply_tools(conv, build, response_text, round_num):
    reads = {}

    for m in TOOL_RE.finditer(response_text):
        tool = m.group(1)
        path_str = (m.group(2) or "").strip()
        body = (m.group(3) or "").strip()

        if tool == "backup_file" and path_str:
            src = Path(path_str) if Path(path_str).is_absolute() else build / path_str
            if src.exists():
                ver = _next_backup_ver(build)
                dst = src.parent / f"{src.stem}_{ver:03d}{src.suffix}"
                shutil.copy2(src, dst)
                print(f"  backed up {src.name} → {dst.name}")

        elif tool == "write_file" and path_str and body:
            dst = Path(path_str) if Path(path_str).is_absolute() else build / path_str
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(body + ("\n" if not body.endswith("\n") else ""))
            print(f"  wrote {dst.relative_to(build)}")

        elif tool == "read_file" and path_str:
            src = Path(path_str) if Path(path_str).is_absolute() else build / path_str
            reads[path_str] = src.read_text() if src.exists() else f"(not found: {path_str})"
            print(f"  read {src.name}")

        elif tool == "write_plan" and body:
            plan_path = conv / "optimization_plan.md"
            current = plan_path.read_text() if plan_path.exists() else ""
            plan_path.write_text(current + f"\n\n---\n{body}\n")
            print(f"  updated optimization_plan.md")

        elif tool == "done":
            print(f"  LLM signaled done for round {round_num}")
            break

    return reads


def _build_ctx(summary, hls_contents, extra_reads, params_text, round_num):
    clock = summary.get("clock_cycles")
    goal = f"**Goal: reduce clock_cycles (currently {clock}). Do NOT attempt to fix numerical accuracy.**"
    lines = [
        f"## Round {round_num} — Current State\n",
        f"{goal}\n\n",
        f"```json\n{json.dumps(summary, indent=2)}\n```\n",
        f"\n## params.yaml\n```yaml\n{params_text}```\n",
        f"\n## Current HLS files\n",
    ]
    for fname, content in hls_contents.items():
        lines.append(f"\n### {fname}\n```cpp\n{content}\n```\n")
    if extra_reads:
        lines.append("\n## Files you requested last round\n")
        for path, content in extra_reads.items():
            lines.append(f"\n### {path}\n```\n{content}\n```\n")
    return "".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

conv = Path(sys.argv[1]).resolve()
max_rounds = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--max-rounds"), 10))

params = yaml.safe_load((conv / "params.yaml").read_text()) or {}
name = params["name"]
io_dir = conv / f"{name}_io"
manifest = json.loads((io_dir / "manifest.json").read_text())

build = conv / "build"
client = Client(monitor_log=build / "monitor.log")

extra_reads = {}
total_cost = 0.0

for round_num in range(1, max_rounds + 1):
    print(f"\n{'='*60}")
    print(f"Optimization round {round_num}/{max_rounds}")
    print(f"{'='*60}")

    summary = _read_summary(build, io_dir, manifest, params)
    print(json.dumps(summary, indent=2))

    hls_contents = _hls_contents(build)
    ctx = _build_ctx(summary, hls_contents, extra_reads, (conv / "params.yaml").read_text(), round_num)

    ver = next_version(build, "llm_response")
    (build / f"prompt_{ver:03d}.txt").write_text(ctx)

    res = client.chat(
        messages=[{"role": "user", "content": [cached(OPTIMIZE_PROMPT), text(ctx)]}],
        system=[cached("You are a Vitis HLS C++ optimization engineer. Respond only with tool calls.")],
    )
    res_text = _strip_fences(res.text)
    round_cost = client.usage.estimate_cost_usd() - total_cost
    total_cost = client.usage.estimate_cost_usd()
    (build / f"llm_response_{ver:03d}.txt").write_text(res_text)
    print(f"  LLM cost this round: ${round_cost:.4f}")

    extra_reads = _apply_tools(conv, build, res_text, round_num)

    if extra_reads:
        print("  LLM requested file reads — will include in next round context")
        continue

    print("  Running C-sim...")
    rc = _run_csim(conv, build, params)
    if rc != 0:
        print(f"  C-sim failed (rc={rc}); see build/csim.log — continuing to next round")
        extra_reads = {"build/csim.log": (build / "csim.log").read_text()[-3000:]}
        continue

    new_summary = _read_summary(build, io_dir, manifest, params)
    _append_summary(build, new_summary, conv)
    print(json.dumps(new_summary, indent=2))

print(f"\nDone after {round_num} rounds. Total cost: ${total_cost:.4f}")
