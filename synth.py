#!/usr/bin/env python3
"""Synthesize an RTL directory with Quartus and print a compact summary."""

from __future__ import annotations

import argparse
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from vrp import infer_top, load_params, verilog_files


EVALUATION_TIMEOUT = 20.0


def find(pattern: str, text: str, default: str = "unknown") -> str:
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else default


def conversion_params(rtl_dir: Path) -> dict:
    paths = sorted(rtl_dir.resolve().parent.glob("*/params.yaml"))
    if not paths:
        return {}
    if len(paths) > 1:
        locations = ", ".join(str(path) for path in paths)
        raise ValueError(f"multiple parameter files found: {locations}")
    return load_params(paths[0].with_name("main.py"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rtl", type=Path)
    parser.add_argument("--top")
    parser.add_argument("--part", help="overrides the part in params.yaml")
    args = parser.parse_args()
    files = verilog_files(args.rtl.resolve())
    top = infer_top(files, args.top)
    params = conversion_params(args.rtl)
    part = args.part or params.get("part")
    if not part:
        raise ValueError("FPGA part is required: use --part or conversion_XXX/*/params.yaml")
    evaluation_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vrp-quartus-") as name:
        work = Path(name)
        lines = [f'set_global_assignment -name FAMILY "Cyclone V"',
                 f"set_global_assignment -name DEVICE {part}",
                 f"set_global_assignment -name TOP_LEVEL_ENTITY {top}",
                 'set_global_assignment -name SDC_FILE "rapid.sdc"']
        for source in files:
            # Some generators put localparam declarations in ANSI parameter
            # lists.  Quartus rejects that construct even in SystemVerilog
            # mode, so normalize temporary synthesis copies to parameters.
            relative = source.relative_to(args.rtl.resolve())
            quartus_source = work / "rtl" / relative
            quartus_source.parent.mkdir(parents=True, exist_ok=True)
            quartus_source.write_text(source.read_text().replace("localparam", "parameter"))
            lines.append(
                f'set_global_assignment -name SYSTEMVERILOG_FILE "{quartus_source}"'
            )
        for source in args.rtl.resolve().iterdir():
            if source.is_file() and source.suffix.lower() in {".hex", ".mif"}:
                shutil.copy2(source, work / source.name)
        (work / "rapid.qsf").write_text("\n".join(lines) + "\n")
        (work / "rapid.qpf").write_text('PROJECT_REVISION = "rapid"\n')
        (work / "rapid.sdc").write_text("create_clock -name aclk -period 10.000 [get_ports aclk]\n")
        print(f"Quartus: compiling {top} for {part} (timeout: {EVALUATION_TIMEOUT:g}s)...",
              file=sys.stderr, flush=True)
        process = subprocess.Popen(
            ["quartus_sh", "--flow", "compile", "rapid"], cwd=work,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=EVALUATION_TIMEOUT)
        except subprocess.TimeoutExpired as timeout_error:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                remaining, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                remaining, _ = process.communicate()
            partial = timeout_error.output or ""
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            output = partial + (remaining or "")
            milestones = [line for line in output.splitlines()
                          if "Running Quartus" in line or "Processing started" in line
                          or "Command:" in line or "Error (" in line]
            if milestones:
                print("\n".join(milestones[-12:]), file=sys.stderr)
            elapsed = time.perf_counter() - evaluation_started
            raise RuntimeError(
                f"Quartus exceeded the {EVALUATION_TIMEOUT:g}s evaluation limit "
                f"({elapsed:.1f}s); RTL is too expensive to compile"
            )
        if process.returncode:
            print("\n".join(output.splitlines()[-40:]), file=sys.stderr)
            raise RuntimeError("Quartus compilation failed")
        fit = (work / "output_files" / "rapid.fit.summary").read_text(errors="replace")
        reports = "\n".join(path.read_text(errors="replace")
                            for path in (work / "output_files").glob("rapid.*.rpt"))

    lut = find(r"Total combinational functions\s*:\s*([\d,]+)", fit)
    dsp = find(r"Total DSP Blocks\s*:\s*([\d,]+)", fit)
    fmax = find(r"([\d.]+\s*MHz)\s*;[^\n]*Restricted Fmax", reports)
    elapsed = time.perf_counter() - evaluation_started
    print(f"evaluation time: {elapsed:.1f}s")
    print(f"LUT: {lut}")
    print(f"DSP: {dsp}")
    print(f"Fmax: {fmax}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"synth.py: {error}", file=sys.stderr)
        raise SystemExit(1)
