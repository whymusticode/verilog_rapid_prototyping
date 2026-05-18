"""run_sim tool: run HLS C-sim and diff against reference."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .. import vivado as vivado_backend

MAX_LOG_TAIL_LINES = 60
MAX_MISMATCH_REPORT = 8


def build_run_sim_tool(ctx):
    from . import Tool

    schema = {
        "name": "run_sim",
        "description": (
            "Run Vitis HLS C simulation from build/hls. Expects hls/tb.cpp "
            "to write sim/sim_diag_out.txt and sim/sim_meta.txt. Diffs against "
            "reference_eigenvalues.txt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top": {
                    "type": "string",
                    "description": "Top HLS function name (default: kernel_top)",
                },
                "tolerance_lsb": {
                    "type": "integer",
                    "description": "Per-element absolute tolerance in LSBs (default: 1)",
                }
            },
            "required": [],
        },
    }

    def handler(args: dict) -> Any:
        return _run_sim(ctx, args)

    return Tool(schema=schema, handler=handler)


def _run_sim(ctx, args: dict) -> dict:
    build = ctx.build_dir
    hls_dir = build / "hls"
    kernel = hls_dir / "kernel.cpp"
    tb = hls_dir / "tb.cpp"
    top = args.get("top") or "kernel_top"
    tolerance = int(args.get("tolerance_lsb", 1))

    if not kernel.exists():
        return {"pass": False, "error": "hls/kernel.cpp not found"}
    if not tb.exists():
        return {"pass": False, "error": "hls/tb.cpp not found"}

    sim_dir = build / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "sim").mkdir(parents=True, exist_ok=True)
    log_path = sim_dir / "csim.log"
    diag_out = sim_dir / "sim_diag_out.txt"
    meta_out = sim_dir / "sim_meta.txt"
    alt_diag = sim_dir / "sim" / "sim_diag_out.txt"
    alt_meta = sim_dir / "sim" / "sim_meta.txt"
    for stale in (log_path, diag_out, meta_out, alt_diag, alt_meta):
        if stale.exists():
            stale.unlink()

    # Keep input path stable for tb.cpp usage.
    project_inputs = ctx.project_dir / "reference_inputs.txt"
    if project_inputs.exists():
        (build / "reference_inputs.txt").write_text(project_inputs.read_text())

    script = _emit_csim_tcl(
        build=build,
        top=top,
        part=ctx.hw_yaml["part"],
        period_ns=float(1000.0 / float(ctx.hw_yaml.get("default_clock_mhz", 100))),
    )
    hls_bin = os.environ.get("VITIS_HLS_BIN", "vitis_hls")
    try:
        proc = vivado_backend.run_exec(
            [hls_bin, "-f", str(script.relative_to(build))],
            cwd=build,
            check=False,
        )
    except Exception as exc:
        return {
            "pass": False,
            "stage": "compile_or_elab",
            "error": f"hls csim launch failed: {exc}",
        }
    log_text = _find_and_capture_csim_log(build, log_path, top)
    log_tail = "\n".join(log_text.splitlines()[-MAX_LOG_TAIL_LINES:])

    if not diag_out.exists() and alt_diag.exists():
        diag_out.write_text(alt_diag.read_text())
    if not meta_out.exists() and alt_meta.exists():
        meta_out.write_text(alt_meta.read_text())

    if proc.returncode != 0 and not diag_out.exists():
        return {
            "pass": False,
            "stage": "runtime",
            "error": "csim returned nonzero and no diag output produced",
            "log_tail": log_tail,
        }

    if not diag_out.exists():
        return {
            "pass": False,
            "stage": "runtime",
            "error": "tb.cpp did not write sim_diag_out.txt",
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

    summary = {
        "pass": cmp["pass"],
        "cache_hit": False,
        "tolerance_lsb": tolerance,
        "n_compared": cmp["n"],
        "n_mismatched": cmp["n_mismatched"],
        "max_abs_err_lsb": cmp["max_abs_err"],
        "first_mismatches": cmp["mismatches"][:MAX_MISMATCH_REPORT],
        "iter_count": meta.get("iter_count"),
        "cycles": meta.get("cycles"),
        "log_tail": log_tail if not cmp["pass"] else log_tail[-1500:],
    }
    (sim_dir / "sim_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _emit_csim_tcl(*, build: Path, top: str, part: str, period_ns: float) -> Path:
    tcl = (
        "open_project hls_csim_prj\n"
        f"set_top {top}\n"
        "add_files hls/kernel.cpp\n"
        "add_files -tb hls/tb.cpp\n"
        "open_solution -reset csim\n"
        f"set_part {{{part}}}\n"
        f"create_clock -period {period_ns:.3f} -name default\n"
        "csim_design\n"
        "exit\n"
    )
    script = build / "run_csim.tcl"
    script.write_text(tcl)
    return script


def _find_and_capture_csim_log(build: Path, log_path: Path, top: str) -> str:
    candidates = [
        build / "hls_csim_prj" / "csim" / "report" / f"{top}_csim.log",
        build / "hls_csim_prj" / "vitis_hls.log",
        build / "vitis_hls.log",
    ]
    for c in candidates:
        if c.exists():
            txt = c.read_text(errors="replace")
            log_path.write_text(txt)
            return txt
    if log_path.exists():
        return log_path.read_text(errors="replace")
    return ""


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
