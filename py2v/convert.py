"""LLM Python→HLS C conversion, csim, and compare against captured I/O.

Usage:
  python py2v/convert.py <conversion_dir>              # call LLM, extract, csim, compare
  python py2v/convert.py <conversion_dir> --from-response  # use build/llm_response.txt (paste workflow)
"""
import json, os, re, subprocess, sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from py2v.client import Client, cached, text

PROMPT = (Path(__file__).parent / "prompts" / "py2hls.md").read_text()
FILE_RE = re.compile(r"=== FILE: ([^\n=]+) ===\n(.*?)(?=\n=== FILE: |\Z)", re.S)
TARGET_RE = re.compile(r"# Translation Target Function\n(.*?)# Translation Target End", re.S)


def _load_tensor(t, path, call=0):
    flat = np.loadtxt(path, ndmin=1)
    if t["complex"]:
        c = flat.reshape(-1, 2)
        flat = c[:, 0] + 1j * c[:, 1]
    shape = tuple(t["shape"])
    n = int(np.prod(shape)) if shape else 1
    return flat[call * n : (call + 1) * n].reshape(shape) if shape else flat[call]


def _compare(ref_dir, sim_dir, manifest, rtol=1e-3, atol=1e-6):
    results = []
    for t in manifest["tensors"]:
        if t["role"] != "out":
            continue
        ref = _load_tensor(t, ref_dir / t["file"])
        sim_p = sim_dir / t["file"]
        if not sim_p.exists():
            results.append({"file": t["file"], "pass": False, "error": "sim output missing"})
            continue
        sim = _load_tensor(t, sim_p)
        ok = np.allclose(ref.real, sim.real, rtol=rtol, atol=atol) and (
            not t["complex"] or np.allclose(ref.imag, sim.imag, rtol=rtol, atol=atol)
        )
        err = float(np.max(np.abs(ref - sim))) if ref.size else 0.0
        results.append({"file": t["file"], "pass": bool(ok), "max_abs_err": err})
    return results


conv = Path(sys.argv[1]).resolve()
from_response = "--from-response" in sys.argv[2:]
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
    res_text = (build / "llm_response.txt").read_text()
    cost = 0.0
else:
    client = Client(monitor_log=build / "monitor.log")
    res = client.chat(
        messages=[{"role": "user", "content": [cached(PROMPT), text(ctx)]}],
        system=[cached("You are a Vitis HLS C++ engineer. Follow the user instructions exactly.")],
    )
    res_text = res.text
    (build / "llm_response.txt").write_text(res_text)
    cost = client.usage.estimate_cost_usd()
    (build / "convert_summary.json").write_text(
        json.dumps({"stop_reason": res.stop_reason, "cost_usd": cost}, indent=2)
    )

files = {m.group(1).strip(): m.group(2).strip() for m in FILE_RE.finditer(res_text)}
if not files:
    sys.exit("no === FILE: ... === blocks in LLM response; see build/llm_response.txt")
for rel, body in files.items():
    p = build / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body + ("\n" if not body.endswith("\n") else ""))
print(f"wrote {len(files)} file(s) under {build}")

part = params["part"]
clk_hz = float(params.get("clock", {}).get("freq_hz", 200e6))
period_ns = 1000.0 / (clk_hz / 1e6)

# Vitis 2025+ dropped the standalone vitis_hls CLI; csim is driven via Python API.
# workspace=conv so tb.cpp's "../<name>_io/" resolves to conv/<name>_io/ correctly.
# Sim outputs land in conv/csim_prj/sim/ and are copied to build/sim/ after.
py_script = f"""\
import vitis, os, shutil
conv = {str(conv)!r}
build = {str(build)!r}
io_name = {(name + '_io')!r}
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

cmp = _compare(io_dir, sim, manifest)
summary = {"pass": all(r["pass"] for r in cmp), "tensors": cmp, "cost_usd": cost}
(sim / "compare_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
sys.exit(0 if summary["pass"] else 1)
