"""run_python_ref tool: execute reference.py with controlled inputs.

This is the LLM's way to (re)generate the reference outputs that the testbench
diffs against. It runs `reference.py` in a subprocess, with a small wrapper
that:
  - generates a deterministic input matrix (seeded numpy)
  - calls a function the reference.py is expected to expose, OR re-runs the
    script as-is if it produces files itself
  - converts the outputs to integer pairs in the project's fixed-point format
  - writes `reference_inputs.txt` and `reference_eigenvalues.txt` into the
    project dir (next to reference.py).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


def build_run_python_ref_tool(ctx):
    from . import Tool

    schema = {
        "name": "run_python_ref",
        "description": (
            "Run the project's reference.py against a deterministic seeded input "
            "and emit `reference_inputs.txt` (one `<re_int> <im_int>` line per "
            "matrix element row-major) and `reference_eigenvalues.txt` (diagonal "
            "of the resulting matrix). Both files are integer pairs at the "
            "project's fixed-point format (W=total_bits, Q=frac_bits)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seed": {
                    "type": "integer",
                    "description": "RNG seed for the input matrix (default: project test_inputs.seed or 0)",
                },
                "n": {
                    "type": "integer",
                    "description": "Matrix size (default: from py2c.yaml MATRIX_SIZE or 10)",
                },
                "max_iter": {
                    "type": "integer",
                    "description": "Override max_iter passed to the reference (default: 1)",
                },
            },
            "required": [],
        },
    }

    def handler(args: dict) -> Any:
        return _run(ctx, args)

    return Tool(schema=schema, handler=handler)


_DRIVER = r"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ref_path = Path(sys.argv[1])
out_inputs = Path(sys.argv[2])
out_diag = Path(sys.argv[3])
n = int(sys.argv[4])
max_iter = int(sys.argv[5])
seed = int(sys.argv[6])
total_bits = int(sys.argv[7])
frac_bits = int(sys.argv[8])

spec = importlib.util.spec_from_file_location("reference", ref_path)
mod = importlib.util.module_from_spec(spec)
# Importing executes the script; that's fine - it may produce its own files,
# we ignore them and use the function it exposes (jacobi_eigen).
try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass

if not hasattr(mod, "jacobi_eigen"):
    print(json.dumps({"error": "reference.py does not expose jacobi_eigen(A, max_iter)"}))
    sys.exit(2)

rng = np.random.default_rng(seed)
BW = 14
vect = (
    rng.integers(-(2 ** BW), 2 ** BW, (n, 100))
    + rng.integers(-(2 ** BW), 2 ** BW, (n, 100)) * 1j
)
acm = vect @ vect.conj().T / (2 ** 14)

scale = 1 << frac_bits
sat_max = (1 << (total_bits - 1)) - 1
sat_min = -(1 << (total_bits - 1))


def to_q(x):
    v = int(round(float(x) * scale))
    return max(sat_min, min(sat_max, v))


with out_inputs.open("w") as f:
    for i in range(n):
        for j in range(n):
            f.write(f"{to_q(acm[i, j].real)} {to_q(acm[i, j].imag)}\n")

result = mod.jacobi_eigen(acm.copy(), max_iter=max_iter)
# The reference signature drifts across PDF versions:
#   (eigvals, eigvecs)         <- original
#   (iters, eigvals, eigvecs)  <- some newer drafts
# Treat the tuple element with shape == (n,) as the eigenvalue vector.
eigvals = None
for elem in result if isinstance(result, tuple) else (result,):
    arr = np.asarray(elem)
    if arr.ndim == 1 and arr.shape[0] == n:
        eigvals = arr
        break
if eigvals is None:
    print(json.dumps({
        "error": "could not locate eigenvalue vector in jacobi_eigen() return",
        "return_shapes": [getattr(np.asarray(e), "shape", None) for e in (result if isinstance(result, tuple) else (result,))],
    }))
    sys.exit(2)

with out_diag.open("w") as f:
    for v in eigvals:
        f.write(f"{to_q(v.real)} {to_q(v.imag)}\n")

print(json.dumps({
    "ok": True,
    "n": n,
    "max_iter": max_iter,
    "seed": seed,
    "fixed_point": {"total_bits": total_bits, "frac_bits": frac_bits},
    "inputs_path": str(out_inputs),
    "diag_path": str(out_diag),
}))
"""


def _run(ctx, args: dict) -> dict:
    ref = ctx.reference_py
    if not ref.exists():
        return {"error": f"reference.py not found: {ref}"}

    seed = int(
        args.get("seed")
        if args.get("seed") is not None
        else ctx.project_yaml.get("test_inputs", {}).get("seed", 0)
    )
    n = int(args.get("n") or _infer_n(ctx) or 10)
    max_iter = int(args.get("max_iter", 1))
    fxp = ctx.project_yaml.get("fixed_point", {})
    total_bits = int(fxp.get("total_bits", 23))
    frac_bits = int(fxp.get("frac_bits", 20))

    inputs_path = ctx.project_dir / "reference_inputs.txt"
    diag_path = ctx.project_dir / "reference_eigenvalues.txt"

    driver_path = ctx.project_dir / ".reference_driver.py"
    driver_path.write_text(_DRIVER)
    proc = subprocess.run(
        [
            sys.executable,
            str(driver_path),
            str(ref),
            str(inputs_path),
            str(diag_path),
            str(n),
            str(max_iter),
            str(seed),
            str(total_bits),
            str(frac_bits),
        ],
        cwd=str(ctx.project_dir),
        capture_output=True,
        text=True,
    )
    driver_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        return {
            "error": "reference driver failed",
            "returncode": proc.returncode,
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-30:]),
        }

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {
            "error": "could not parse driver output",
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-30:]),
        }
    return result


def _infer_n(ctx) -> int | None:
    py2c_path = ctx.project_dir / "py2c.yaml"
    if not py2c_path.exists():
        return None
    text = py2c_path.read_text()
    for line in text.splitlines():
        if "MATRIX_SIZE" in line:
            continue
        s = line.strip()
        if s.startswith("value:") and s.endswith(("0", "8", "6", "4")):
            try:
                return int(s.split(":", 1)[1].strip())
            except ValueError:
                continue
    return None
