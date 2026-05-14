"""run_sim tool: compile + run xsim, diff against reference, return summary."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..cache import file_sha256, read_json, stable_hash, vivado_cache_dir, write_json
from .. import vivado as vivado_backend


XSIM_LOG_TAIL_LINES = 60
MAX_MISMATCH_REPORT = 8


def build_run_sim_tool(ctx):
    from . import Tool

    schema = {
        "name": "run_sim",
        "description": (
            "Compile RTL+TB with xvlog/xelab and run xsim. The TB is expected to "
            "write `sim_diag_out.txt` (one `<re> <im>` integer pair per line) and "
            "may write `sim_meta.txt` with `iter_count <N>` and `cycles <N>`. "
            "The handler diffs `sim_diag_out.txt` against the Python reference "
            "diagonal (`reference_eigenvalues.txt`) at integer-LSB tolerance and "
            "returns a small JSON summary. Pass `tolerance_lsb` to relax."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "string",
                    "description": "TB top module name (default: tb_top)",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "RTL source files relative to the buildspace (default: all rtl/*.v)",
                },
                "tb": {
                    "type": "string",
                    "description": "Testbench file relative to buildspace (default: tb/tb_top.v)",
                },
                "tolerance_lsb": {
                    "type": "integer",
                    "description": "Per-element absolute tolerance in LSBs (default: 1)",
                },
            },
            "required": [],
        },
    }

    def handler(args: dict) -> Any:
        return _run_sim(ctx, args)

    return Tool(schema=schema, handler=handler)


def _run_sim(ctx, args: dict) -> dict:
    build = ctx.build_dir
    top = args.get("top") or "tb_top"
    tb = build / (args.get("tb") or "tb/tb_top.v")
    src_args = args.get("sources")
    if src_args:
        sources = [build / s for s in src_args]
    else:
        sources = sorted((build / "rtl").glob("*.v"))
    tolerance = int(args.get("tolerance_lsb", 1))

    if not tb.exists():
        return {"pass": False, "error": f"tb not found: {tb.relative_to(build)}"}
    if not sources:
        return {"pass": False, "error": "no rtl sources found under rtl/"}

    sim_dir = build / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    # Some TBs write to "sim/<file>" while already running under build/sim.
    # Pre-create this nested directory so writes don't fail.
    (sim_dir / "sim").mkdir(parents=True, exist_ok=True)
    log_path = sim_dir / "xsim.log"
    diag_out = sim_dir / "sim_diag_out.txt"
    meta_out = sim_dir / "sim_meta.txt"
    for stale in (log_path, diag_out, meta_out):
        if stale.exists():
            stale.unlink()

    # Testbenches typically run from build/sim and read ../reference_inputs.txt.
    # Mirror the project-level reference vectors into build/ so this path works.
    project_inputs = ctx.project_dir / "reference_inputs.txt"
    if project_inputs.exists():
        shutil.copy2(project_inputs, build / "reference_inputs.txt")

    rel_sources = [str(s.relative_to(build)) for s in sources]
    rel_tb = str(tb.relative_to(build))

    script = _build_xsim_script(top, rel_sources, rel_tb)
    script_path = sim_dir / "run_xsim.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)
    cache_key = _sim_cache_key(
        top=top,
        tolerance=tolerance,
        tb=tb,
        sources=sources,
        project_dir=ctx.project_dir,
    )
    cached = _restore_sim_cache(cache_key, sim_dir)
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    try:
        proc = vivado_backend.run_exec(
            ["bash", "sim/run_xsim.sh"],
            cwd=build,
            check=False,
        )
    except Exception as exc:
        return {"pass": False, "error": f"vivado backend failed: {exc}"}

    raw_log = ""
    if log_path.exists():
        raw_log = log_path.read_text(errors="replace")
    log_tail = "\n".join(raw_log.splitlines()[-XSIM_LOG_TAIL_LINES:])

    # Some generated TBs write under sim/sim_diag_out.txt while already
    # running from build/sim (so the actual path becomes build/sim/sim/...).
    # Normalize these back to the canonical build/sim paths.
    alt_diag = sim_dir / "sim" / "sim_diag_out.txt"
    alt_meta = sim_dir / "sim" / "sim_meta.txt"
    if not diag_out.exists() and alt_diag.exists():
        shutil.copy2(alt_diag, diag_out)
    if not meta_out.exists() and alt_meta.exists():
        shutil.copy2(alt_meta, meta_out)

    if proc.returncode != 0 and not diag_out.exists():
        return {
            "pass": False,
            "stage": "compile_or_elab",
            "error": "xsim returned nonzero and no diag output produced",
            "log_tail": log_tail,
        }

    if not diag_out.exists():
        return {
            "pass": False,
            "stage": "runtime",
            "error": f"TB did not write {diag_out.name}",
            "log_tail": log_tail,
        }

    ref_diag = ctx.project_dir / "reference_eigenvalues.txt"
    if not ref_diag.exists():
        return {
            "pass": False,
            "stage": "reference",
            "error": "reference_eigenvalues.txt missing; run python_ref first",
            "log_tail": log_tail,
        }

    cmp = _diff_diagonals(diag_out, ref_diag, tolerance)
    meta = _read_meta(meta_out)

    cycles = _scrape_cycles(raw_log)
    if meta.get("cycles") is not None:
        cycles = meta["cycles"]

    summary = {
        "pass": cmp["pass"],
        "cache_hit": False,
        "tolerance_lsb": tolerance,
        "n_compared": cmp["n"],
        "n_mismatched": cmp["n_mismatched"],
        "max_abs_err_lsb": cmp["max_abs_err"],
        "first_mismatches": cmp["mismatches"][:MAX_MISMATCH_REPORT],
        "iter_count": meta.get("iter_count"),
        "cycles": cycles,
        "log_tail": log_tail if not cmp["pass"] else log_tail[-1500:],
    }
    (sim_dir / "sim_summary.json").write_text(json.dumps(summary, indent=2))
    if summary["pass"]:
        _save_sim_cache(cache_key, sim_dir, summary)
    return summary


def _build_xsim_script(top: str, sources: list[str], tb: str) -> str:
    """Bash script invoked inside the vivado backend (docker / flatpak / native).

    Output goes to `sim/xsim.log` (relative to cwd, which is the buildspace).
    """
    src_quoted = " ".join(f'"{s}"' for s in sources)
    return (
        "#!/usr/bin/env bash\n"
        "set -o pipefail\n"
        "mkdir -p sim\n"
        "cd sim\n"
        "{\n"
        f"  xvlog -sv ../{tb} {' '.join('../' + s for s in sources)} \\\n"
        "    && xelab " + top + " -s " + top + "_sim -debug typical \\\n"
        "    && xsim " + top + "_sim -runall ;\n"
        "} 2>&1 | tee xsim.log\n"
    )


def _diff_diagonals(sim_path: Path, ref_path: Path, tol: int) -> dict:
    """Compare two files of `<re_int> <im_int>` lines."""
    sim_pairs = _parse_int_pairs(sim_path)
    ref_pairs = _parse_int_pairs(ref_path)
    n = min(len(sim_pairs), len(ref_pairs))
    mismatches = []
    max_abs = 0
    n_mis = 0
    for i in range(n):
        sre, sim_im = sim_pairs[i]
        rre, rim = ref_pairs[i]
        de, di = abs(sre - rre), abs(sim_im - rim)
        max_abs = max(max_abs, de, di)
        if de > tol or di > tol:
            n_mis += 1
            mismatches.append(
                {
                    "index": i,
                    "sim_re": sre,
                    "sim_im": sim_im,
                    "ref_re": rre,
                    "ref_im": rim,
                    "abs_err_re": de,
                    "abs_err_im": di,
                }
            )
    if len(sim_pairs) != len(ref_pairs):
        mismatches.append(
            {
                "index": -1,
                "note": f"length mismatch sim={len(sim_pairs)} ref={len(ref_pairs)}",
            }
        )
    return {
        "pass": (n_mis == 0) and (len(sim_pairs) == len(ref_pairs)),
        "n": n,
        "n_mismatched": n_mis,
        "max_abs_err": max_abs,
        "mismatches": mismatches,
    }


def _parse_int_pairs(path: Path) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            out.append((int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    return out


def _read_meta(meta_path: Path) -> dict:
    out: dict[str, Any] = {}
    if not meta_path.exists():
        return out
    for line in meta_path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            out[parts[0]] = int(parts[1])
        except ValueError:
            out[parts[0]] = parts[1]
    return out


_CYCLES_RE = re.compile(r"\bcycles\s*=\s*(\d+)\b", re.IGNORECASE)


def _scrape_cycles(log: str) -> int | None:
    for line in reversed(log.splitlines()):
        m = _CYCLES_RE.search(line)
        if m:
            return int(m.group(1))
    return None


def _sim_cache_key(
    *,
    top: str,
    tolerance: int,
    tb: Path,
    sources: list[Path],
    project_dir: Path,
) -> str:
    ref_inputs = project_dir / "reference_inputs.txt"
    ref_diag = project_dir / "reference_eigenvalues.txt"
    payload = {
        "schema": "sim-cache-v1",
        "top": top,
        "tolerance_lsb": tolerance,
        "tb_hash": file_sha256(tb),
        "rtl_hashes": {str(p): file_sha256(p) for p in sorted(sources, key=str)},
        "reference_inputs_hash": file_sha256(ref_inputs) if ref_inputs.exists() else None,
        "reference_diag_hash": file_sha256(ref_diag) if ref_diag.exists() else None,
        "backend_identity": vivado_backend.backend_identity(),
        "tool_version_stamp": "sim-cache-v1",
    }
    return stable_hash(payload, namespace="vivado-sim-v1")


def _sim_cache_dir(cache_key: str) -> Path:
    return vivado_cache_dir() / "sim" / cache_key


def _restore_sim_cache(cache_key: str, sim_dir: Path) -> dict | None:
    cache_dir = _sim_cache_dir(cache_key)
    metadata = read_json(cache_dir / "meta.json")
    summary = read_json(cache_dir / "sim_summary.json")
    if not metadata or not summary:
        return None
    if not metadata.get("pass", False):
        return None
    for filename in ("xsim.log", "sim_diag_out.txt", "sim_meta.txt", "sim_summary.json"):
        src = cache_dir / filename
        if src.exists():
            shutil.copy2(src, sim_dir / filename)
    print(f"[py2v-cache] run_sim cache hit: {cache_dir}")
    return summary


def _save_sim_cache(cache_key: str, sim_dir: Path, summary: dict[str, Any]) -> None:
    cache_dir = _sim_cache_dir(cache_key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("xsim.log", "sim_diag_out.txt", "sim_meta.txt", "sim_summary.json"):
        src = sim_dir / filename
        if src.exists():
            shutil.copy2(src, cache_dir / filename)
    write_json(
        cache_dir / "meta.json",
        {
            "schema": "sim-cache-v1",
            "pass": bool(summary.get("pass")),
            "cache_key": cache_key,
        },
    )
    print(f"[py2v-cache] run_sim cache saved: {cache_dir}")
