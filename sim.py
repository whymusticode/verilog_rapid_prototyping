#!/usr/bin/env python3
"""Generate a fixed-point testbench and compare RTL with a Python target."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from vrp import (fraction_bits, infer_top, lanes, load_params, load_reference,
                 pack_hex, quantize, unpack_signed, verilog_files)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="project directory containing main.py and params.yaml")
    parser.add_argument("rtl", type=Path)
    parser.add_argument("--top")
    parser.add_argument("--tests", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=100_000, help="cycles per vector")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--io", type=Path,
                        help="generated-testbench directory (default: conversion_XXX/IO)")
    return parser.parse_args()


def make_tb(top: str, in_lanes: int, out_lanes: int, tests: int, timeout: int,
            width: int, frac: int, count: int) -> str:
    x_width, y_width = count * in_lanes * width, count * out_lanes * width
    return f"""`timescale 1ns/1ps
module tb;
  reg clk = 0; always #5 clk = ~clk;
  reg rst = 1;
  reg s_axis_tvalid = 0, s_axis_tlast = 0;
  wire s_axis_tready;
  reg [{x_width - 1}:0] x_vector;
  reg [{in_lanes * width - 1}:0] s_axis_tdata;
  wire m_axis_tvalid, m_axis_tlast;
  reg m_axis_tready = 1;
  wire [{out_lanes * width - 1}:0] m_axis_tdata;
  reg [{y_width - 1}:0] y_vector;
  integer fd, rc, i, j, waited, cycles = 0, start_cycle;
  {top} #(.WIDTH({width}), .FRAC({frac}), .N({count}),
          .IN_LANES({in_lanes}), .OUT_LANES({out_lanes})) dut(
            .aclk(clk), .aresetn(!rst),
            .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
            .s_axis_tdata(s_axis_tdata), .s_axis_tlast(s_axis_tlast),
            .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
            .m_axis_tdata(m_axis_tdata), .m_axis_tlast(m_axis_tlast));
  always @(posedge clk) cycles <= cycles + 1;
  initial begin
    fd = $fopen("vectors.hex", "r");
    if (!fd) $fatal(1, "cannot open vectors.hex");
    repeat (4) @(posedge clk); rst <= 0;
    for (i = 0; i < {tests}; i = i + 1) begin
      start_cycle = cycles;
      rc = $fscanf(fd, "%h\\n", x_vector);
      if (rc != 1) $fatal(1, "bad input vector %0d", i);
      for (j = 0; j < {count}; j = j + 1) begin
        s_axis_tdata <= x_vector[j*{in_lanes * width} +: {in_lanes * width}];
        s_axis_tlast <= (j == {count}-1);
        s_axis_tvalid <= 1;
        @(posedge clk); while (!s_axis_tready) @(posedge clk);
      end
      s_axis_tvalid <= 0; s_axis_tlast <= 0;
      waited = 0;
      for (j = 0; j < {count}; j = j + 1) begin
        while (!m_axis_tvalid && waited < {timeout}) begin @(negedge clk); waited = waited + 1; end
        if (!m_axis_tvalid) $fatal(1, "timeout waiting for output %0d", i);
        if (m_axis_tlast != (j == {count}-1)) $fatal(1, "bad TLAST on output %0d", j);
        y_vector[j*{out_lanes * width} +: {out_lanes * width}] = m_axis_tdata;
        @(negedge clk);
      end
      $display("RESULT %0d %0d %h", i, cycles-start_cycle, y_vector);
      @(posedge clk);
    end
    $fclose(fd); $finish;
  end
endmodule
"""


def main() -> int:
    evaluation_started = time.perf_counter()
    args = arguments()
    project_dir = args.project.resolve()
    if not project_dir.is_dir():
        raise ValueError(f"project directory does not exist: {args.project}")
    reference = project_dir / "main.py"
    if not reference.is_file():
        raise ValueError(f"project entry point does not exist: {reference}")
    rtl_dir = args.rtl.resolve()
    conversion_dir = rtl_dir.parent
    reference_copy = conversion_dir / project_dir.name
    if project_dir != reference_copy:
        shutil.copytree(
            project_dir,
            reference_copy,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    params = load_params(reference)
    bits = int(params.get("bits", 16))
    if bits < 2:
        raise ValueError("bits must be at least 2")
    count = int(params.get("N", 1))
    rng = np.random.default_rng(args.seed)
    np.random.seed(args.seed)
    module = load_reference(reference, params)
    readings = getattr(module, "_vrp_readings", [])
    if readings:
        if len(readings) < args.tests:
            raise ValueError(f"main.py made {len(readings)} target readings, but --tests={args.tests}")
        inputs = [x for x, _ in readings[:args.tests]]
        expected = [y for _, y in readings[:args.tests]]
    elif (stimulus := getattr(module, "inputs", None)) is not None:
        inputs = [np.asarray(v) for v in stimulus(rng, args.tests)]
        if len(inputs) != args.tests:
            raise ValueError(f"inputs(rng, count) returned {len(inputs)} vectors, expected {args.tests}")
        expected = [np.asarray(module.target(v)) for v in inputs]
    else:
        inputs = [rng.uniform(-1, 1, count) for _ in range(args.tests)]
        expected = [np.asarray(module.target(v)) for v in inputs]
    frac = fraction_bits([*inputs, *expected], bits)
    q_inputs = [quantize(v, bits, frac) for v in inputs]
    out_lanes = len(lanes(expected[0]))
    if any(len(lanes(v)) != out_lanes for v in expected):
        raise ValueError("target output shape changed between readings")
    files = verilog_files(rtl_dir)
    top = infer_top(files, args.top)

    work = (args.io or conversion_dir / "IO").resolve()
    work.mkdir(parents=True, exist_ok=True)
    for asset in rtl_dir.iterdir():
        if asset.is_file() and asset.suffix.lower() in {".hex", ".mif"}:
            shutil.copy2(asset, work / asset.name)
    (work / "vectors.hex").write_text("\n".join(pack_hex(v, bits) for v in q_inputs) + "\n")
    tb = work / "tb.sv"
    in_lanes = len(q_inputs[0]) // count
    if out_lanes % count:
        raise ValueError("target output must contain N real/complex samples")
    tb.write_text(make_tb(top, in_lanes, out_lanes // count, args.tests,
                          args.timeout, bits, frac, count))
    compile_cmd = ["iverilog", "-g2012", "-Wall", "-s", "tb", "-o",
                   str(work / "sim.vvp"), str(tb), *map(str, files)]
    subprocess.run(compile_cmd, check=True, cwd=work)
    run = subprocess.run(["vvp", str(work / "sim.vvp")], check=True, cwd=work,
                         text=True, capture_output=True)

    results: dict[int, tuple[int, str]] = {}
    for line in run.stdout.splitlines():
        if line.startswith("RESULT "):
            _, index, cycles, value = line.split()
            results[int(index)] = (int(cycles), value)
    if len(results) != args.tests:
        print(run.stdout, end="", file=sys.stderr)
        raise RuntimeError(f"simulation returned {len(results)} of {args.tests} results")
    errors, signals, cycle_counts = [], [], []
    for index, want in enumerate(expected):
        cycle, text = results[index]
        cycle_counts.append(cycle)
        got = unpack_signed(text, out_lanes, bits) / (1 << frac)
        want_lanes = lanes(want)
        errors.extend((got - want_lanes).tolist())
        signals.extend(want_lanes.tolist())
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    peak = float(np.max(np.abs(signals)))
    precision = float("inf") if rmse == 0 else np.log2(peak / rmse) if peak else float("-inf")
    elapsed = time.perf_counter() - evaluation_started
    print(f"evaluation time: {elapsed:.1f}s")
    print(f"average clock cycles: {np.mean(cycle_counts):.1f}")
    print(f"fraction bits: {frac}")
    print(f"bits of precision: {precision:.3g}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"sim.py: {error}", file=sys.stderr)
        raise SystemExit(1)
