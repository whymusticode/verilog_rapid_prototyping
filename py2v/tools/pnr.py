"""run_pnr tool: run HLS synthesis, parse csynth reports."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .. import vivado as vivado_backend


def build_run_pnr_tool(ctx):
    from . import Tool

    schema = {
        "name": "run_pnr",
        "description": (
            "Run Vitis HLS C synthesis (csynth) for build/hls/kernel.cpp and parse "
            "latency/timing/resource estimates. phase is accepted for API compatibility."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": ["synth", "impl"],
                    "description": "Accepted for compatibility; HLS path always runs csynth.",
                },
                "clock_mhz": {
                    "type": "number",
                    "description": "Override clock frequency for the timing constraint (default: hw default)",
                },
                "top": {
                    "type": "string",
                    "description": "HLS top function name (default: kernel_top)",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Unused for HLS mode.",
                },
            },
            "required": [],
        },
    }

    def handler(args: dict) -> Any:
        return _run_pnr(ctx, args)

    return Tool(schema=schema, handler=handler)


def _run_pnr(ctx, args: dict) -> dict:
    build = ctx.build_dir
    phase = args.get("phase") or "synth"
    top = args.get("top") or "kernel_top"
    clock_mhz = float(
        args.get("clock_mhz")
        or ctx.project_yaml.get("clock_mhz")
        or ctx.hw_yaml.get("default_clock_mhz", 100)
    )
    period_ns = round(1000.0 / clock_mhz, 3)

    hls_dir = build / "hls"
    kernel_cpp = hls_dir / "kernel.cpp"
    if not kernel_cpp.exists():
        return {"pass": False, "error": "hls/kernel.cpp not found"}

    reports_dir = build / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / f"hls_{phase}.log"
    if log_path.exists():
        log_path.unlink()

    script = _emit_hls_tcl(
        build=build,
        top=top,
        part=ctx.hw_yaml["part"],
        period_ns=period_ns,
    )
    hls_bin = os.environ.get("VITIS_HLS_BIN", "vitis_hls")
    script_arg = str(script.relative_to(build))
    hls_cmd = [hls_bin, "-f", script_arg]
    if Path(hls_bin).name == "vitis-run":
        hls_cmd = [hls_bin, "--mode", "hls", "--tcl", script_arg]
    try:
        proc = vivado_backend.run_exec(
            hls_cmd,
            cwd=build,
            check=False,
        )
    except Exception as exc:
        return {"pass": False, "error": f"hls backend failed: {exc}"}

    raw_log = ""
    if log_path.exists():
        raw_log = log_path.read_text(errors="replace")
    else:
        raw_log = _find_and_capture_hls_log(build, reports_dir, phase)

    csynth = _find_csynth_report(build, top)
    metrics = _parse_csynth(csynth)
    errors = _scrape_errors(raw_log)
    pass_ok = proc.returncode == 0 and metrics.get("estimated_clock_ns") is not None

    summary = {
        "pass": pass_ok,
        "phase": phase,
        "mode": "hls_csynth",
        "clock_mhz": clock_mhz,
        "period_ns": period_ns,
        "wns_ns": None,
        "fmax_mhz": metrics.get("fmax_mhz"),
        "latency_cycles": metrics.get("latency_cycles"),
        "util": {
            "lut_as_logic": {"used": metrics.get("lut", 0), "pct": None},
            "block_ram_tile": {"used": metrics.get("bram", 0), "pct": None},
            "dsps": {"used": metrics.get("dsp", 0), "pct": None},
        },
        "errors": errors[:10],
        "log_tail": "\n".join(raw_log.splitlines()[-80:]),
    }
    (reports_dir / f"pnr_summary_{phase}.json").write_text(json.dumps(summary, indent=2))
    return summary


def _emit_hls_tcl(*, build: Path, top: str, part: str, period_ns: float) -> Path:
    tcl = (
        "open_project hls_prj\n"
        f"set_top {top}\n"
        "add_files hls/kernel.cpp\n"
        "add_files -tb hls/tb.cpp\n"
        "open_solution -reset sol1\n"
        f"set_part {{{part}}}\n"
        f"create_clock -period {period_ns} -name default\n"
        "csim_design\n"
        "csynth_design\n"
        "exit\n"
    )
    script = build / "run_hls.tcl"
    script.write_text(tcl)
    return script


_ERROR_RE = re.compile(r"^(ERROR|CRITICAL WARNING):\s*(.+)$")


def _scrape_errors(log: str) -> list[dict]:
    out: list[dict] = []
    for line in log.splitlines():
        m = _ERROR_RE.match(line.strip())
        if m:
            out.append({"severity": m.group(1), "msg": m.group(2)[:300]})
    return out


def _find_and_capture_hls_log(build: Path, reports_dir: Path, phase: str) -> str:
    # Vitis HLS default log names.
    candidates = [
        build / "hls_prj" / "sol1" / "csynth.log",
        build / "hls_prj" / "vitis_hls.log",
        build / "vitis_hls.log",
    ]
    for c in candidates:
        if c.exists():
            text = c.read_text(errors="replace")
            (reports_dir / f"hls_{phase}.log").write_text(text)
            return text
    return ""


def _find_csynth_report(build: Path, top: str) -> Path | None:
    c = build / "hls_prj" / "sol1" / "syn" / "report" / f"{top}_csynth.rpt"
    if c.exists():
        return c
    d = build / "hls_prj" / "sol1" / "syn" / "report"
    if d.exists():
        reports = sorted(d.glob("*_csynth.rpt"))
        if reports:
            return reports[0]
    return None


def _parse_csynth(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    text = path.read_text(errors="replace")
    est_clk = None
    lat = None
    dsp = lut = bram = 0

    m_clk = re.search(r"Estimated\s+Clock\s+Period\s*:\s*([0-9.]+)", text, re.I)
    if m_clk:
        est_clk = float(m_clk.group(1))
    m_lat = re.search(r"Latency\s*\(cycles\)\s*min\s*=\s*(\d+)", text, re.I)
    if m_lat:
        lat = int(m_lat.group(1))
    m_dsp = re.search(r"\bDSP\s*\|\s*(\d+)\s*\|", text)
    if m_dsp:
        dsp = int(m_dsp.group(1))
    m_lut = re.search(r"\bLUT\s*\|\s*(\d+)\s*\|", text)
    if m_lut:
        lut = int(m_lut.group(1))
    m_bram = re.search(r"\bBRAM_18K\s*\|\s*(\d+)\s*\|", text)
    if m_bram:
        bram = int(m_bram.group(1))

    fmax = round(1000.0 / est_clk, 2) if est_clk and est_clk > 0 else None
    return {
        "estimated_clock_ns": est_clk,
        "fmax_mhz": fmax,
        "latency_cycles": lat,
        "dsp": dsp,
        "lut": lut,
        "bram": bram,
    }
