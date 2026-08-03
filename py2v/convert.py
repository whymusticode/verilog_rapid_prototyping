"""LLM Python→HLS C or Verilog conversion, sim, and compare against captured I/O.

Usage:
  python py2v/convert.py <conversion_dir>                       # HLS C++ / Vitis csim (default)
  python py2v/convert.py <conversion_dir> --backend verilog     # SystemVerilog / iverilog
  python py2v/convert.py <conversion_dir> --from-response       # use latest llm_response_NNN.txt
"""
import json, os, re, subprocess, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from py2v.client import Client, cached, text
from py2v.util import compare, git_hash, next_version
from py2v.gen_tb import generate as gen_tb_hls
from py2v.gen_tb_v import generate as gen_tb_v

FILE_RE = re.compile(r"=== FILE: ([^\n=]+) ===\n(.*?)(?=\n=== FILE: |\Z)", re.S)
TARGET_RE = re.compile(r"# Translation Target Function\n(.*?)# Translation Target End", re.S)


conv = Path(sys.argv[1]).resolve()
from_response = "--from-response" in sys.argv[2:]
backend = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--backend"), "hls")
assert backend in ("hls", "verilog"), f"unknown --backend {backend!r}"
PROMPT = (Path(__file__).parent / "prompts" / ("py2verilog.md" if backend == "verilog" else "py2hls.md")).read_text()
params = yaml.safe_load((conv / "params.yaml").read_text()) or {}
name = params["name"]
io_dir = conv / f"{name}_io"
manifest = json.loads((io_dir / "manifest.json").read_text())
py_target = TARGET_RE.search((conv / f"{name}.py").read_text()).group(1).strip()

build = conv / "build"
hls = build / "hls"
sim = build / "sim"
hls.mkdir(parents=True, exist_ok=True)
sim.mkdir(parents=True, exist_ok=True)

ctx = (
    f"## params.yaml\n```yaml\n{(conv / 'params.yaml').read_text()}```\n\n"
    f"## manifest.json\n```json\n{json.dumps(manifest, indent=2)}```\n\n"
    f"## Translation target `{manifest['target']}`\n```python\n{py_target}\n```\n\n"
    f"IO directory (absolute path): `{io_dir}/`\n"
    f"Sim output directory (absolute path): `{sim}/`\n"
)

if from_response:
    existing = sorted(build.glob("llm_response_*.txt"))
    res_text = existing[-1].read_text() if existing else (build / "llm_response.txt").read_text()
    cost = 0.0
else:
    ver = next_version(build, "llm_response")
    client = Client(monitor_log=build / "monitor.log")
    (build / f"prompt_{ver:03d}.txt").write_text(ctx)
    system_prompt = ("You are a Verilog/SystemVerilog design engineer. Follow the user instructions exactly."
                      if backend == "verilog" else
                      "You are a Vitis HLS C++ engineer. Follow the user instructions exactly.")
    res = client.chat(
        messages=[{"role": "user", "content": [cached(PROMPT), text(ctx)]}],
        system=[cached(system_prompt)],
        max_tokens=32768 if backend == "verilog" else None,
    )
    res_text = res.text
    (build / f"llm_response_{ver:03d}.txt").write_text(res_text)
    cost = client.usage.estimate_cost_usd()

# Extract kernel files from LLM response (tb is generated, never from the LLM)
tb_name = "tb.sv" if backend == "verilog" else "tb.cpp"
files = {m.group(1).strip(): m.group(2).strip() for m in FILE_RE.finditer(res_text)}
files = {k: v for k, v in files.items() if tb_name not in k}
if not files:
    sys.exit("no === FILE: ... === blocks in LLM response; see latest llm_response_NNN.txt")
for rel, body in files.items():
    p = build / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body + ("\n" if not body.endswith("\n") else ""))
print(f"wrote {len(files)} file(s) from LLM under {build}")

if backend == "verilog":
    tb_src = gen_tb_v(manifest, params, io_dir, sim)
    (hls / "tb.sv").write_text(tb_src)
    print("generated tb.sv")

    env = os.environ.copy()
    sim_bin = build / "sim.out"
    compile_proc = subprocess.run(
        ["iverilog", "-g2012", "-I", str(hls), "-o", str(sim_bin),
         str(hls / "kernel.sv"), str(hls / "tb.sv")],
        cwd=str(conv), env=env, capture_output=True, text=True,
    )
    log = (compile_proc.stdout or "") + (compile_proc.stderr or "")
    if compile_proc.returncode != 0:
        (build / "csim.log").write_text(log)
        print(f"iverilog compile failed (rc={compile_proc.returncode}); see build/csim.log")
        sys.exit(compile_proc.returncode)

    run_proc = subprocess.run(
        ["vvp", str(sim_bin)],
        cwd=str(conv), env=env, capture_output=True, text=True,
    )
    log += (run_proc.stdout or "") + (run_proc.stderr or "")
    (build / "csim.log").write_text(log)
    if run_proc.returncode != 0:
        print(f"vvp run failed (rc={run_proc.returncode}); see build/csim.log")
        sys.exit(run_proc.returncode)
else:
    tb_src = gen_tb_hls(manifest, io_dir, sim)
    (hls / "tb.cpp").write_text(tb_src)
    print(f"generated tb.cpp")

    part = params["part"]
    clk_hz = float(params.get("clock", {}).get("freq_hz", 200e6))
    period_ns = 1000.0 / (clk_hz / 1e6)

    # Vitis 2025+ dropped the standalone vitis_hls CLI; csim is driven via Python API.
    # workspace=conv so tb.cpp's IO paths resolve correctly.
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
    # useful for debugging vitis interface:
    (build / "csim.log").write_text((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode != 0:
        print(f"csim failed (rc={proc.returncode}); see build/csim.log")
        sys.exit(proc.returncode)

cmp = compare(io_dir, sim, manifest, params=params)
clock_cycles_path = sim / "clock_cycles.txt"
clock_cycles = int(clock_cycles_path.read_text().strip()) if clock_cycles_path.exists() else None
summary = {"tensors": cmp, "clock_cycles": clock_cycles, "cost_usd": cost, "git": git_hash(conv)}

history_path = build / "summary.json"
history = json.loads(history_path.read_text()) if history_path.exists() else []
if not isinstance(history, list):
    history = [history]
history.append(summary)
history_path.write_text(json.dumps(history, indent=2))
print(json.dumps(summary, indent=2))
sys.exit(0)
