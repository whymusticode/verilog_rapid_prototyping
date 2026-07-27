"""Capture a project's Translation Target Function inputs/outputs for arbitrary calls.

Usage: python py2v/capture.py <project_script.py> [out_dir]

Runs the script as __main__ and records every call to the marked target
function (its bound arguments and its return value) without modifying the
reference code. Works for any signature / return type via a profile hook.

Output format is friendly to both Python and HLS C++:
  <out_dir>/<role>_<name>.txt   one value per line, all calls stacked (call-major);
                                complex flattened to interleaved real,imag.
  <out_dir>/manifest.json       per-tensor {role,name,dtype,complex,shape,count,file}.
A C++ testbench reads each .txt with `ifstream >>`; Python reloads via the manifest.
"""
import copy, json, re, runpy, sys
from pathlib import Path

import numpy as np

script = Path(sys.argv[1]).resolve()
out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else script.with_name(script.stem + "_io")

# target = first `def NAME` after the marker comment
target = re.search(r"# *Translation Target Function\s*\n\s*def\s+(\w+)", script.read_text()).group(1)

calls, stack = [], []
def _profile(frame, event, arg):
    if frame.f_code.co_name != target:
        return
    if event == "call":
        co = frame.f_code
        names = co.co_varnames[: co.co_argcount + co.co_kwonlyargcount]
        rec = {"inputs": copy.deepcopy({n: frame.f_locals[n] for n in names})}
        calls.append(rec); stack.append(rec)
    elif event == "return" and stack:
        stack.pop()["outputs"] = copy.deepcopy(arg)

sys.setprofile(_profile)
try:
    runpy.run_path(str(script), run_name="__main__")
finally:
    sys.setprofile(None)

# flatten each call into named ("role","name") tensors; outputs tuples -> out0,out1,...
def _tensors(call):
    for n, v in call["inputs"].items():
        yield "in", n, v
    o = call["outputs"]
    seq = o if isinstance(o, (tuple, list)) else (o,)
    for i, v in enumerate(seq):
        yield "out", (str(i) if len(seq) > 1 else ""), v

out_dir.mkdir(parents=True, exist_ok=True)
groups = {}                                            # (role,name) -> list of arrays per call
for c in calls:
    for role, name, v in _tensors(c):
        groups.setdefault((role, name), []).append(np.asarray(v))

manifest = []
for (role, name), arrs in groups.items():
    a = np.stack(arrs)                                 # (count, *shape)
    is_cplx = np.iscomplexobj(a)
    flat = a.ravel()
    flat = np.column_stack([flat.real, flat.imag]).ravel() if is_cplx else flat
    fname = f"{role}_{name}.txt" if name != "" else f"{role}.txt"
    np.savetxt(out_dir / fname, flat, fmt="%.17g")
    manifest.append({"role": role, "name": name, "dtype": str(a.dtype),
                     "complex": bool(is_cplx), "shape": list(a.shape[1:]),
                     "count": int(a.shape[0]), "file": fname})

(out_dir / "manifest.json").write_text(json.dumps({"target": target, "tensors": manifest}, indent=2))
print(f"{out_dir}: {len(calls)} call(s) of {target}() -> {len(manifest)} tensor file(s)")
