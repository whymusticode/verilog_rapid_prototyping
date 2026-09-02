#!/usr/bin/env python3
"""Synthesize an RTL directory with Quartus and print a compact summary."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from vrp import infer_top, load_params, verilog_files


def find(pattern: str, text: str, default: str = "unknown") -> str:
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rtl", type=Path)
    parser.add_argument("--top")
    parser.add_argument("--part", help="overrides the part in params.yaml")
    args = parser.parse_args()
    files = verilog_files(args.rtl.resolve())
    top = infer_top(files, args.top)
    # The conversion directory is normally next to Projects/*, so permit either
    # a colocated params file or an explicit --part.
    params_path = next((parent / "params.yaml" for parent in [args.rtl, *args.rtl.parents]
                        if (parent / "params.yaml").exists()), None)
    params = load_params(params_path.with_name("reference.py")) if params_path else {}
    part = args.part or params.get("part")
    if not part:
        raise ValueError("FPGA part is required: use --part or put part in RTL/params.yaml")

    with tempfile.TemporaryDirectory(prefix="vrp-quartus-") as name:
        work = Path(name)
        lines = [f'set_global_assignment -name FAMILY "Cyclone V"',
                 f"set_global_assignment -name DEVICE {part}",
                 f"set_global_assignment -name TOP_LEVEL_ENTITY {top}",
                 'set_global_assignment -name SDC_FILE "rapid.sdc"']
        for source in files:
            kind = "SYSTEMVERILOG_FILE" if source.suffix == ".sv" else "VERILOG_FILE"
            lines.append(f'set_global_assignment -name {kind} "{source}"')
        (work / "rapid.qsf").write_text("\n".join(lines) + "\n")
        (work / "rapid.qpf").write_text('PROJECT_REVISION = "rapid"\n')
        (work / "rapid.sdc").write_text("create_clock -name aclk -period 10.000 [get_ports aclk]\n")
        run = subprocess.run(["quartus_sh", "--flow", "compile", "rapid"], cwd=work,
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if run.returncode:
            print("\n".join(run.stdout.splitlines()[-40:]), file=sys.stderr)
            raise RuntimeError("Quartus compilation failed")
        fit = (work / "output_files" / "rapid.fit.summary").read_text(errors="replace")
        reports = "\n".join(path.read_text(errors="replace")
                            for path in (work / "output_files").glob("rapid.*.rpt"))

    lut = find(r"Total combinational functions\s*:\s*([\d,]+)", fit)
    dsp = find(r"Total DSP Blocks\s*:\s*([\d,]+)", fit)
    fmax = find(r"([\d.]+\s*MHz)\s*;[^\n]*Restricted Fmax", reports)
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
