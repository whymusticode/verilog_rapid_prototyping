"""run_pnr tool: run vivado synth (and optionally impl), parse reports."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from ..cache import file_sha256, read_json, stable_hash, vivado_cache_dir, write_json
from .. import vivado as vivado_backend


def build_run_pnr_tool(ctx):
    from . import Tool

    schema = {
        "name": "run_pnr",
        "description": (
            "Render a build.tcl from project + hw, then run Vivado in batch mode. "
            "phase=\"synth\" stops after synth_design; phase=\"impl\" runs through "
            "place_design + route_design + report_timing_summary + report_utilization. "
            "Returns {pass, wns_ns, fmax_mhz, util, errors[]}. Reports are written "
            "under reports/."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": ["synth", "impl"],
                    "description": "Stop after synth, or run through impl (default: synth)",
                },
                "clock_mhz": {
                    "type": "number",
                    "description": "Override clock frequency for the timing constraint (default: hw default)",
                },
                "top": {
                    "type": "string",
                    "description": "Top module name (default: top)",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "RTL source files (default: all rtl/*.v)",
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
    if phase not in ("synth", "impl"):
        return {"pass": False, "error": f"invalid phase: {phase}"}
    top = args.get("top") or "top"
    clock_mhz = float(
        args.get("clock_mhz")
        or ctx.project_yaml.get("clock_mhz")
        or ctx.hw_yaml.get("default_clock_mhz", 100)
    )
    period_ns = round(1000.0 / clock_mhz, 3)

    src_args = args.get("sources")
    if src_args:
        sources = [build / s for s in src_args]
    else:
        sources = sorted((build / "rtl").glob("*.v"))
    if not sources:
        return {"pass": False, "error": "no rtl sources found under rtl/"}

    reports_dir = build / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / f"vivado_{phase}.log"
    if log_path.exists():
        log_path.unlink()

    xdc_path = _emit_xdc(ctx, build, period_ns)
    tcl_path = _emit_tcl(
        ctx,
        build,
        sources=[s.relative_to(build) for s in sources],
        xdc=xdc_path.relative_to(build),
        top=top,
        phase=phase,
    )
    cache_key = _pnr_cache_key(
        phase=phase,
        top=top,
        clock_mhz=clock_mhz,
        part=ctx.hw_yaml["part"],
        sources=sources,
        xdc_path=xdc_path,
        backend_identity=vivado_backend.backend_identity(),
    )
    cached = _restore_pnr_cache(cache_key, reports_dir, phase, log_path)
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    try:
        proc = vivado_backend.run(
            [
                "-mode",
                "batch",
                "-nojournal",
                "-log",
                f"reports/vivado_{phase}.log",
                "-source",
                str(tcl_path.relative_to(build)),
            ],
            cwd=build,
            check=False,
        )
    except Exception as exc:
        return {"pass": False, "error": f"vivado backend failed: {exc}"}

    raw_log = ""
    if log_path.exists():
        raw_log = log_path.read_text(errors="replace")
    errors = _scrape_errors(raw_log)

    timing = _parse_timing(reports_dir / f"timing_{phase}.rpt")
    util = _parse_util(reports_dir / f"util_{phase}.rpt")

    pass_ok = proc.returncode == 0 and not errors
    if phase == "impl" and timing.get("wns_ns") is not None and timing["wns_ns"] < 0:
        pass_ok = False

    summary = {
        "pass": pass_ok,
        "cache_hit": False,
        "phase": phase,
        "clock_mhz": clock_mhz,
        "period_ns": period_ns,
        "wns_ns": timing.get("wns_ns"),
        "fmax_mhz": timing.get("fmax_mhz"),
        "util": util,
        "errors": errors[:10],
        "log_tail": "\n".join(raw_log.splitlines()[-80:]),
    }
    (reports_dir / f"pnr_summary_{phase}.json").write_text(json.dumps(summary, indent=2))
    if summary["pass"]:
        _save_pnr_cache(cache_key, reports_dir, phase, summary, build)
    return summary


def _emit_xdc(ctx, build: Path, period_ns: float) -> Path:
    """Emit a minimal timing-only XDC (or copy the hw preset's XDC if any)."""
    constraints_dir = build / "constraints"
    constraints_dir.mkdir(parents=True, exist_ok=True)
    xdc_path = constraints_dir / "timing.xdc"

    src_xdc = ctx.hw_yaml.get("constraints", {}).get("xdc")
    if src_xdc:
        # Allow xdc paths relative to repo root (project_dir.parent.parent).
        src = Path(src_xdc)
        if not src.is_absolute():
            src = ctx.project_dir.parent.parent / src
        if src.exists():
            xdc_path.write_text(src.read_text())
            return xdc_path

    xdc_path.write_text(
        "# auto-generated timing-only XDC\n"
        f"create_clock -name clk -period {period_ns} [get_ports clk]\n"
    )
    return xdc_path


def _emit_tcl(
    ctx,
    build: Path,
    *,
    sources: list[Path],
    xdc: Path,
    top: str,
    phase: str,
) -> Path:
    part = ctx.hw_yaml["part"]
    reports_dir = "reports"
    src_lines = "\n".join(f"read_verilog {s}" for s in sources)
    tcl = f"""\
set_param general.maxThreads 4
read_verilog -sv {xdc}
""".replace("read_verilog -sv", "read_xdc")
    # The above is a template hack; build the real tcl below.
    tcl = (
        f"set_part {part}\n"
        f"set_param general.maxThreads 4\n"
        f"{src_lines}\n"
        f"read_xdc {xdc}\n"
        f"synth_design -top {top} -part {part}\n"
        f"report_utilization -file {reports_dir}/util_synth.rpt\n"
        f"report_timing_summary -file {reports_dir}/timing_synth.rpt\n"
    )
    if phase == "impl":
        tcl += (
            "opt_design\n"
            "place_design\n"
            "route_design\n"
            f"report_utilization -file {reports_dir}/util_impl.rpt\n"
            f"report_timing_summary -file {reports_dir}/timing_impl.rpt\n"
        )
    tcl_path = build / "build.tcl"
    tcl_path.write_text(tcl)
    return tcl_path


_ERROR_RE = re.compile(r"^(ERROR|CRITICAL WARNING):\s*(.+)$")


def _scrape_errors(log: str) -> list[dict]:
    out: list[dict] = []
    for line in log.splitlines():
        m = _ERROR_RE.match(line.strip())
        if m:
            out.append({"severity": m.group(1), "msg": m.group(2)[:300]})
    return out


_WNS_RE = re.compile(r"WNS\s*:?\s*(-?\d+\.\d+)\s*ns", re.IGNORECASE)
_WNS_TBL_RE = re.compile(r"^\s*(-?\d+\.\d+)\s+", re.MULTILINE)


def _parse_timing(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    wns: Optional[float] = None
    m = _WNS_RE.search(text)
    if m:
        wns = float(m.group(1))
    else:
        m2 = re.search(r"WNS.*?\n[-\s]+\n\s*(-?\d+\.\d+)", text, re.DOTALL)
        if m2:
            wns = float(m2.group(1))
    if wns is None:
        return {}
    fmax_mhz = None
    period_match = re.search(r"-period\s+(\d+\.\d+)", text)
    if period_match:
        period = float(period_match.group(1))
        achieved = period - wns
        if achieved > 0:
            fmax_mhz = round(1000.0 / achieved, 2)
    return {"wns_ns": wns, "fmax_mhz": fmax_mhz}


_UTIL_ROWS = ("Slice LUTs", "LUT as Logic", "Slice Registers", "DSPs", "Block RAM Tile")


def _parse_util(path: Path) -> dict:
    if not path.exists():
        return {}
    out: dict[str, Any] = {}
    for line in path.read_text(errors="replace").splitlines():
        for label in _UTIL_ROWS:
            if label in line:
                m = re.search(r"\|\s*(\d+)\s*\|.*\|\s*(\d+\.\d+)\s*\|", line)
                if m:
                    out[label.lower().replace(" ", "_")] = {
                        "used": int(m.group(1)),
                        "pct": float(m.group(2)),
                    }
    return out


def _pnr_cache_key(
    *,
    phase: str,
    top: str,
    clock_mhz: float,
    part: str,
    sources: list[Path],
    xdc_path: Path,
    backend_identity: dict[str, str],
) -> str:
    payload = {
        "schema": "pnr-cache-v1",
        "phase": phase,
        "top": top,
        "clock_mhz": clock_mhz,
        "part": part,
        "rtl_hashes": {str(p): file_sha256(p) for p in sorted(sources, key=str)},
        "xdc_hash": file_sha256(xdc_path),
        "backend_identity": backend_identity,
        "tool_version_stamp": "pnr-cache-v1",
    }
    return stable_hash(payload, namespace="vivado-pnr-v1")


def _pnr_cache_dir(cache_key: str) -> Path:
    return vivado_cache_dir() / "pnr" / cache_key


def _restore_pnr_cache(
    cache_key: str,
    reports_dir: Path,
    phase: str,
    log_path: Path,
) -> dict | None:
    cache_dir = _pnr_cache_dir(cache_key)
    summary = read_json(cache_dir / f"pnr_summary_{phase}.json")
    metadata = read_json(cache_dir / "meta.json")
    if not summary or not metadata:
        return None
    if not metadata.get("pass", False):
        return None
    reports_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        f"vivado_{phase}.log",
        f"timing_{phase}.rpt",
        f"util_{phase}.rpt",
        f"pnr_summary_{phase}.json",
    ):
        src = cache_dir / filename
        if src.exists():
            shutil.copy2(src, reports_dir / filename)
    if not log_path.exists() and (reports_dir / f"vivado_{phase}.log").exists():
        shutil.copy2(reports_dir / f"vivado_{phase}.log", log_path)
    print(f"[py2v-cache] run_pnr cache hit: {cache_dir}")
    return summary


def _save_pnr_cache(
    cache_key: str,
    reports_dir: Path,
    phase: str,
    summary: dict[str, Any],
    build_dir: Path,
) -> None:
    cache_dir = _pnr_cache_dir(cache_key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        f"vivado_{phase}.log",
        f"timing_{phase}.rpt",
        f"util_{phase}.rpt",
        f"pnr_summary_{phase}.json",
    ):
        src = reports_dir / filename
        if src.exists():
            shutil.copy2(src, cache_dir / filename)
    build_tcl = build_dir / "build.tcl"
    timing_xdc = build_dir / "constraints" / "timing.xdc"
    if build_tcl.exists():
        shutil.copy2(build_tcl, cache_dir / "build.tcl")
    if timing_xdc.exists():
        shutil.copy2(timing_xdc, cache_dir / "timing.xdc")
    write_json(
        cache_dir / "meta.json",
        {
            "schema": "pnr-cache-v1",
            "pass": bool(summary.get("pass")),
            "cache_key": cache_key,
            "phase": phase,
        },
    )
    print(f"[py2v-cache] run_pnr cache saved: {cache_dir}")
