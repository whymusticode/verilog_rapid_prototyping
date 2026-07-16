"""Shared utilities for convert.py and optimize.py."""
import math, subprocess
from pathlib import Path
import numpy as np


def load_tensor(t, path, call=0):
    flat = np.loadtxt(path, ndmin=1)
    if t["complex"]:
        c = flat.reshape(-1, 2)
        flat = c[:, 0] + 1j * c[:, 1]
    shape = tuple(t["shape"])
    n = int(np.prod(shape)) if shape else 1
    return flat[call * n : (call + 1) * n].reshape(shape) if shape else flat[call]


def _err_bits(max_abs_err, fraction):
    if max_abs_err == 0.0:
        return 0
    return round(math.log2(max_abs_err) + fraction, 2)


def _out_params(manifest, params):
    """Map output tensor file → fraction bits, by declaration order in params.yaml."""
    out_keys = list((params.get("output") or {}).keys())
    mapping = {}
    out_idx = 0
    for t in manifest["tensors"]:
        if t["role"] != "out":
            continue
        key = out_keys[out_idx] if out_idx < len(out_keys) else None
        mapping[t["file"]] = params["output"][key].get("fraction", 0) if key else 0
        out_idx += 1
    return mapping


def compare(ref_dir, sim_dir, manifest, params=None):
    out_fractions = _out_params(manifest, params or {}) if params else {}
    results = []
    for t in manifest["tensors"]:
        if t["role"] != "out":
            continue
        ref = load_tensor(t, ref_dir / t["file"])
        sim_p = Path(sim_dir) / t["file"]
        if not sim_p.exists():
            results.append({"file": t["file"], "max_abs_err": None, "max_abs_err_bits": None})
            continue
        sim = load_tensor(t, sim_p)
        err = float(np.max(np.abs(ref - sim))) if ref.size else 0.0
        fraction = out_fractions.get(t["file"], 0)
        results.append({
            "file": t["file"],
            "max_abs_err": err,
            "max_abs_err_bits": _err_bits(err, fraction),
        })
    return results


def git_hash(repo_dir):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def next_version(build, prefix):
    """Return the next unused NNN index for versioned log files."""
    existing = list(Path(build).glob(f"{prefix}_*.txt"))
    indices = []
    for p in existing:
        try:
            indices.append(int(p.stem.split("_")[-1]))
        except ValueError:
            pass
    return max(indices, default=-1) + 1
