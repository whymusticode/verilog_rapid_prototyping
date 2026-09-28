#!/usr/bin/env python3
"""Generate a streaming fixed-point testbench and compare RTL with a Python target."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from vrp import (fraction_bits, infer_top, lanes, load_params, load_reference,
                 pack_hex, quantize, unpack_signed, verilog_files)


DEFAULT_ACLK_PS = 10_000


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conversion", type=Path,
                        help="conversion directory containing rtl/ and python/")
    parser.add_argument("project", type=Path, nargs="?",
                        help="override Python project (default: conversion/python)")
    parser.add_argument("--top")
    parser.add_argument("--tests", type=int, default=10, help="frames streamed back to back")
    parser.add_argument("--timeout", type=int, default=100_000,
                        help="fail after this many cycles without an AXI handshake")
    parser.add_argument("--rate", type=float, default=0,
                        help="input beats per second (0 streams as fast as TREADY allows; "
                             "default: 0, so measured throughput is not capped by the target)")
    parser.add_argument("--fifo", type=int, default=0,
                        help="report crossing FIFO overflow above this many beats")
    parser.add_argument("--drain-stall", type=int, default=0, metavar="PERCENT",
                        help="percentage of cycles the output sink deasserts TREADY")
    parser.add_argument("--io", type=Path,
                        help="generated-testbench directory (default: conversion_XXX/IO)")
    return parser.parse_args()


def make_tb(top: str, in_lanes: int, out_lanes: int, frames: int, count: int,
            width: int, frac: int, aclk_ps: int, beat_ps: int, fifo_limit: int,
            drain_stall: int, idle_limit: int) -> str:
    return f"""`timescale 1ps/1ps
// Streaming AXI4-Stream harness.
//
// Frames are streamed back to back: the master keeps offering beats while the
// receiver has produced them, the sink keeps draining, and neither side waits
// for the other.  A design is therefore free to overlap the transform of one
// frame with the arrival of the next, and is required to hold its output
// stable whenever the sink applies backpressure.
module tb;
  localparam integer WIDTH       = {width};
  localparam integer FRAC        = {frac};
  localparam integer N           = {count};
  localparam integer IN_LANES    = {in_lanes};
  localparam integer OUT_LANES   = {out_lanes};
  localparam integer FRAMES      = {frames};
  localparam integer IN_W        = IN_LANES * WIDTH;
  localparam integer OUT_W       = OUT_LANES * WIDTH;
  localparam integer BEATS       = FRAMES * N;
  localparam integer ACLK_PS     = {aclk_ps};
  localparam integer BEAT_PS     = {beat_ps};
  localparam integer FIFO_LIMIT  = {fifo_limit};
  localparam integer DRAIN_STALL = {drain_stall};
  localparam integer IDLE_LIMIT  = {idle_limit};

  reg aclk = 0;
  always #(ACLK_PS / 2) aclk = ~aclk;
  reg aresetn = 0;

  reg [IN_W-1:0] stimulus [0:BEATS-1];

  reg              s_axis_tvalid = 0;
  reg              s_axis_tlast  = 0;
  reg  [IN_W-1:0]  s_axis_tdata  = 0;
  wire             s_axis_tready;
  wire             m_axis_tvalid;
  wire             m_axis_tlast;
  wire [OUT_W-1:0] m_axis_tdata;
  reg              m_axis_tready = 0;

  {top} #(.WIDTH(WIDTH), .FRAC(FRAC), .N(N),
          .IN_LANES(IN_LANES), .OUT_LANES(OUT_LANES)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tlast(s_axis_tlast),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .m_axis_tdata(m_axis_tdata), .m_axis_tlast(m_axis_tlast));

  integer cycle = 0;
  always @(posedge aclk) if (aresetn) cycle <= cycle + 1;

  integer in_file, out_file;
  time    stream_start;

  initial begin
    $readmemh("vectors.hex", stimulus);
    in_file  = $fopen("input.log",  "w");
    out_file = $fopen("output.log", "w");
    if (!in_file || !out_file) $fatal(1, "cannot open the testbench logs");
    repeat (8) @(posedge aclk);
    @(negedge aclk);
    aresetn = 1;
    stream_start = $time;
  end

  // Receive-clock source and clock-domain-crossing buffer.
  //
  // A radio front end delivers one beat every BEAT_PS and never pauses, so
  // beat k has arrived once simulation time reaches stream_start + k*BEAT_PS.
  // Everything between that source and the DUT is the crossing FIFO, whose
  // occupancy is the number of beats that arrived but were not accepted on
  // aclk.  Deriving arrival from time rather than from a second simulated
  // clock keeps the crossing free of simulator races while still measuring
  // the buffering a real crossing has to provide.
  integer arrived = 0, sent = 0, level = 0, fifo_peak = 0;
  reg     fifo_overflow = 0;
  integer next_sent, next_arrived;
  time    produced;

  always @(posedge aclk) begin
    if (!aresetn) begin
      arrived <= 0; sent <= 0; level <= 0;
      s_axis_tvalid <= 0; s_axis_tlast <= 0; s_axis_tdata <= 0;
    end else begin
      next_sent = sent;
      if (s_axis_tvalid && s_axis_tready) begin
        $fwrite(in_file, "%0d %0d\\n", sent, cycle);
        next_sent = sent + 1;
      end
      if (BEAT_PS == 0) next_arrived = BEATS;
      else begin
        produced = ($time - stream_start) / BEAT_PS + 1;
        next_arrived = (produced > BEATS) ? BEATS : produced;
      end
      level = next_arrived - next_sent;
      if (level > fifo_peak) fifo_peak <= level;
      if (FIFO_LIMIT > 0 && level > FIFO_LIMIT) fifo_overflow <= 1;
      // AXI4-Stream forbids withdrawing or altering an offered beat, so only
      // reload the payload once the current one has been accepted.
      if (!(s_axis_tvalid && !s_axis_tready)) begin
        if (next_sent < BEATS && level > 0) begin
          s_axis_tvalid <= 1;
          s_axis_tdata  <= stimulus[next_sent];
          s_axis_tlast  <= ((next_sent % N) == N - 1);
        end else begin
          s_axis_tvalid <= 0;
          s_axis_tlast  <= 0;
        end
      end
      arrived <= next_arrived;
      sent    <= next_sent;
    end
  end

  // Output sink: drains continuously, optionally applying random backpressure.
  integer received = 0, stalls = 0;
  integer unsigned roll;
  reg              held_valid = 0, held_ready = 0, held_last = 0;
  reg [OUT_W-1:0] held_data = 0;

  always @(posedge aclk) begin
    if (!aresetn) begin
      received <= 0; stalls <= 0;
      held_valid <= 0; held_ready <= 0;
      m_axis_tready <= 1;
    end else begin
      if (held_valid && !held_ready) begin
        if (!m_axis_tvalid)
          $fatal(1, "M_AXIS TVALID withdrawn without a handshake at cycle %0d", cycle);
        if (m_axis_tdata !== held_data || m_axis_tlast !== held_last)
          $fatal(1, "M_AXIS payload changed while backpressured at cycle %0d", cycle);
      end
      if (m_axis_tvalid && m_axis_tready) begin
        if (m_axis_tlast !== ((received % N) == N - 1))
          $fatal(1, "M_AXIS TLAST was %0b on output beat %0d, expected %0b: %0d frames of N=%0d beats stream back to back, so TLAST marks every Nth beat, not the end of the stream",
                 m_axis_tlast, received, ((received % N) == N - 1), FRAMES, N);
        $fwrite(out_file, "%0d %0d %h\\n", received, cycle, m_axis_tdata);
        received <= received + 1;
      end else if (m_axis_tvalid && !m_axis_tready)
        stalls <= stalls + 1;
      held_valid <= m_axis_tvalid; held_ready <= m_axis_tready;
      held_data  <= m_axis_tdata;  held_last  <= m_axis_tlast;
      if (DRAIN_STALL == 0) m_axis_tready <= 1;
      else begin
        roll = $urandom;
        m_axis_tready <= ((roll % 100) >= DRAIN_STALL);
      end
    end
  end

  integer progress = 0;
  always @(posedge aclk) if (aresetn) begin
    if ((s_axis_tvalid && s_axis_tready) || (m_axis_tvalid && m_axis_tready))
      progress <= cycle;
    else if (cycle - progress > IDLE_LIMIT)
      $fatal(1, "no AXI handshake for %0d cycles after %0d of %0d output beats",
             IDLE_LIMIT, received, BEATS);
    if (received == BEATS) begin
      $display("SUMMARY cycles=%0d fifo_peak=%0d fifo_overflow=%0d stalls=%0d",
               cycle, fifo_peak, fifo_overflow, stalls);
      $fclose(in_file); $fclose(out_file);
      $finish;
    end
  end
endmodule
"""


def stimulus_and_expected(module, rng, params: dict, count: int,
                          tests: int) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Return the input frames and the reference frames they must produce."""
    readings = getattr(module, "_vrp_readings", [])
    if readings:
        if len(readings) < tests:
            raise ValueError(f"main.py made {len(readings)} target readings, but --tests={tests}")
        return [x for x, _ in readings[:tests]], [y for _, y in readings[:tests]]
    if (stimulus := getattr(module, "inputs", None)) is not None:
        inputs = [np.asarray(v) for v in stimulus(rng, tests)]
        if len(inputs) != tests:
            raise ValueError(f"inputs(rng, count) returned {len(inputs)} vectors, expected {tests}")
    else:
        inputs = [rng.uniform(-1, 1, count) for _ in range(tests)]
    # A design that carries state between frames - a polyphase filter bank
    # holds FIR history, for instance - cannot be modelled by resetting the
    # reference for every frame.  ``stream`` lets a project describe the whole
    # back-to-back sequence; ``target`` remains the memoryless shorthand.
    if (streamer := getattr(module, "stream", None)) is not None:
        expected = [np.asarray(y) for y in streamer(inputs)]
        if len(expected) != tests:
            raise ValueError(f"stream(frames) returned {len(expected)} frames, expected {tests}")
        return inputs, expected
    return inputs, [np.asarray(module.target(v)) for v in inputs]


def beat_interval(params: dict, count: int, rate: float | None, aclk_ps: int) -> tuple[int, float]:
    """Return the picoseconds between input beats and the rate they represent."""
    if rate is None:
        target = params.get("target") or {}
        frequency, cycles = target.get("frequency"), target.get("cycles")
        if not frequency or not cycles:
            return 0, 0.0
        rate = count * float(frequency) / float(cycles)
    if rate <= 0:
        return 0, 0.0
    interval = round(1e12 / rate)
    if interval <= aclk_ps // 2:
        raise ValueError(f"input rate {rate:g} beats/s is faster than one beat per aclk cycle")
    return interval, rate


def read_log(path: Path, columns: int) -> list[list[str]]:
    rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    if any(len(row) != columns for row in rows):
        raise RuntimeError(f"{path.name} is malformed")
    return rows


def main() -> int:
    evaluation_started = time.perf_counter()
    args = arguments()
    conversion_dir = args.conversion.resolve()
    project_arg = args.project or conversion_dir / "python"
    project_dir = project_arg.resolve()
    if args.project is None and conversion_dir not in project_dir.parents:
        raise ValueError(f"python link must point inside the conversion: {project_arg}")
    if not project_dir.is_dir():
        raise ValueError(f"project directory does not exist: {project_arg}")
    reference = project_dir / "main.py"
    if not reference.is_file():
        raise ValueError(f"project entry point does not exist: {reference}")
    rtl_dir = conversion_dir / "rtl"
    params = load_params(reference)
    bits = int(params.get("bits", 16))
    if bits < 2:
        raise ValueError("bits must be at least 2")
    count = int(params.get("N", 1))
    if not 0 <= args.drain_stall < 100:
        raise ValueError("--drain-stall must be a percentage below 100")
    rng = np.random.default_rng()
    module = load_reference(reference, params)
    inputs, expected = stimulus_and_expected(module, rng, params, count, args.tests)
    frac = fraction_bits([*inputs, *expected], bits)
    q_inputs = [quantize(v, bits, frac) for v in inputs]
    out_lanes = len(lanes(expected[0]))
    if any(len(lanes(v)) != out_lanes for v in expected):
        raise ValueError("target output shape changed between readings")
    if out_lanes % count:
        raise ValueError("target output must contain N real/complex samples")
    in_lanes = len(q_inputs[0]) // count
    out_lanes //= count
    files = verilog_files(rtl_dir)
    top = infer_top(files, args.top)

    target = params.get("target") or {}
    aclk_ps = DEFAULT_ACLK_PS
    if target.get("frequency"):
        aclk_ps = max(2, 2 * round(5e11 / float(target["frequency"])))
    beat_ps, rate = beat_interval(params, count, args.rate, aclk_ps)

    work = (args.io or conversion_dir / "IO").resolve()
    work.mkdir(parents=True, exist_ok=True)
    for asset in rtl_dir.iterdir():
        if asset.is_file() and asset.suffix.lower() in {".hex", ".mif", ".mem"}:
            shutil.copy2(asset, work / asset.name)
    beats = [pack_hex(frame[index * in_lanes:(index + 1) * in_lanes], bits)
             for frame in q_inputs for index in range(count)]
    (work / "vectors.hex").write_text("\n".join(beats) + "\n")
    tb = work / "tb.sv"
    # Without a modelled arrival rate every beat is available immediately, so
    # the crossing occupancy is meaningless and cannot overflow.
    fifo_limit = args.fifo if beat_ps else 0
    tb.write_text(make_tb(top, in_lanes, out_lanes, args.tests, count, bits, frac,
                          aclk_ps, beat_ps, fifo_limit, args.drain_stall,
                          args.timeout))
    for stale in ("input.log", "output.log"):
        (work / stale).unlink(missing_ok=True)
    compile_cmd = ["iverilog", "-g2012", "-Wall", "-s", "tb", "-o",
                   str(work / "sim.vvp"), str(tb), *map(str, files)]
    subprocess.run(compile_cmd, check=True, cwd=work)
    run = subprocess.run(["vvp", str(work / "sim.vvp")], cwd=work, text=True,
                         capture_output=True)

    summary = {}
    for line in run.stdout.splitlines():
        if line.startswith("SUMMARY "):
            summary = dict(field.split("=", 1) for field in line.split()[1:])
    outputs = read_log(work / "output.log", 3) if (work / "output.log").exists() else []
    if len(outputs) != args.tests * count or not summary:
        print(run.stdout, end="", file=sys.stderr)
        print(run.stderr, end="", file=sys.stderr)
        raise RuntimeError(
            f"simulation produced {len(outputs)} of {args.tests * count} output beats")
    accepted = read_log(work / "input.log", 2)

    errors, signals = [], []
    for index, want in enumerate(expected):
        got = np.concatenate([unpack_signed(outputs[index * count + beat][2], out_lanes, bits)
                              for beat in range(count)]) / (1 << frac)
        want_lanes = lanes(want)
        errors.extend((got - want_lanes).tolist())
        signals.extend(want_lanes.tolist())
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    worst = sorted(range(len(errors)), key=lambda i: abs(errors[i]), reverse=True)[:12]
    (work / "errors.json").write_text(json.dumps({
        "rmse": rmse, "worst": [
            {"frame": i // (count * out_lanes), "sample": (i // out_lanes) % count,
             "lane": i % out_lanes, "expected": signals[i],
             "actual": signals[i] + errors[i], "error": errors[i]}
            for i in worst]}, indent=2) + "\n")
    peak = float(np.max(np.abs(signals)))
    precision = float("inf") if rmse == 0 else np.log2(peak / rmse) if peak else float("-inf")

    frame_in = [int(accepted[(f + 1) * count - 1][1]) for f in range(args.tests)]
    frame_out = [int(outputs[(f + 1) * count - 1][1]) for f in range(args.tests)]
    latency = max(out - inp for inp, out in zip(frame_in, frame_out))
    if args.tests > 1:
        throughput = (frame_out[-1] - frame_out[0]) / (args.tests - 1)
    else:
        throughput = float(frame_out[0])
    fifo_peak = int(summary.get("fifo_peak", 0))
    overflowed = summary.get("fifo_overflow", "0") != "0"

    elapsed = time.perf_counter() - evaluation_started
    print(f"evaluation time: {elapsed:.1f}s")
    print(f"input rate: {'unthrottled' if not beat_ps else f'{rate / 1e6:.4g} MS/s'}")
    print(f"throughput: {throughput:.1f} cycles/frame")
    print(f"latency: {latency} cycles")
    if beat_ps:
        print(f"crossing FIFO: {fifo_peak} beats"
              + (f" of {fifo_limit}" if fifo_limit else "")
              + (" OVERFLOW" if overflowed else ""))
    print(f"fraction bits: {frac}")
    print(f"bits of precision: {precision:.9g}")
    print(f"RMS error: {rmse:.9g}")
    print(f"numerical diagnostics: {work / 'errors.json'}")
    for i in worst[:3]:
        print(f"  frame {i // (count * out_lanes)}, sample {(i // out_lanes) % count}, "
              f"lane {i % out_lanes}: expected {signals[i]:.8g}, "
              f"got {signals[i] + errors[i]:.8g}, error {errors[i]:.8g}")
    budget = target.get("cycles")
    if budget:
        print(f"cycle target: {budget} cycles/frame; measured/target: {throughput / float(budget):.9g}")
    # Exit status is about measurement validity, never a performance threshold.
    return 1 if run.returncode != 0 else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"sim.py: {error}", file=sys.stderr)
        raise SystemExit(1)
