#!/usr/bin/env python3
"""Stream a project's input through the RTL and compare its output stream.

The project (main.py) supplies the whole input stream and the expected output
stream (vrp.load_stream). The RTL chooses how many scalars travel per AXI beat
with its own IN_LANES and OUT_LANES parameter defaults; the harness packs and
unpacks accordingly. There are no frames, no TLAST and no padding: every
output beat is compared, in order, with the next expected scalars.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

import xilinx
from vrp import (Stream, infer_top, load_params, load_reference, load_stream, measure,
                 pack_hex, quantize_format, top_parameters, unpack, verilog_files)


DEFAULT_ACLK_PS = 10_000
# Parameters the harness supplies when the top module declares them.
SUPPLIED = ("WIDTH", "FRAC", "N", "IN_WIDTH", "IN_FRAC", "OUT_WIDTH", "OUT_FRAC")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conversion", type=Path, nargs="?",
                        help="conversion directory containing rtl/ and python/")
    parser.add_argument("project", type=Path, nargs="?",
                        help="override Python project (default: conversion/python)")
    parser.add_argument("-p", "--generate", type=Path, metavar="PROJECT",
                        help="only write PROJECT's input and expected output streams "
                             "(no RTL, no simulation) to --io, default PROJECT/IO")
    parser.add_argument("--top")
    parser.add_argument("--samples", type=int,
                        help="input samples measured (default: params sim_samples, else 10*N, "
                             "else 163840); later input keeps flowing so partial beats complete")
    parser.add_argument("--timeout", type=int, default=100_000,
                        help="fail after this many cycles without an AXI handshake")
    parser.add_argument("--rate", type=float, default=0,
                        help="input samples per second (0, the default, streams as fast as "
                             "TREADY allows, so throughput measures design capacity)")
    parser.add_argument("--fifo", type=int, default=0,
                        help="report crossing FIFO overflow above this many beats")
    parser.add_argument("--drain-stall", type=int, default=0, metavar="PERCENT",
                        help="percentage of cycles the output sink deasserts TREADY")
    parser.add_argument("--io", type=Path,
                        help="generated-testbench directory (default: conversion_XXX/IO)")
    parser.add_argument("--simulator", choices=("xsim", "iverilog"), default="xsim",
                        help="xsim (default; several times faster on long streams) or iverilog "
                             "(no startup cost, for tiny runs)")
    parser.add_argument("--seed", type=int,
                        help="stimulus RNG seed (default: fresh; the seed used is recorded in errors.json)")
    args = parser.parse_args()
    if (args.conversion is None) == (args.generate is None):
        parser.error("give either a conversion directory or -p PROJECT")
    return args


def default_samples(params: dict) -> int:
    if params.get("sim_samples"):
        return int(params["sim_samples"])
    return 10 * int(params["N"]) if params.get("N") else 163_840


def make_tb(top: str, supplied: dict[str, int], in_lanes: int, out_lanes: int,
            in_width: int, out_width: int, in_beats: int, out_beats: int, aclk_ps: int,
            beat_ps: int, fifo_limit: int, drain_stall: int, idle_limit: int) -> str:
    dut_parameters = "".join(f"  localparam integer {name} = {value}; // DUT parameter\n"
                             for name, value in supplied.items() if name not in ("IN_LANES", "OUT_LANES"))
    overrides = ", ".join(f".{name}({name})" for name in supplied)
    lanes_note = {name: " // DUT parameter" if name in supplied else "" for name in ("IN_LANES", "OUT_LANES")}
    return f"""`timescale 1ps/1ps
// Streaming AXI4-Stream harness.
//
// The input stream is offered beat by beat while the sink drains output
// continuously; neither side waits for the other. There are no frames and no
// TLAST. Each input beat carries IN_LANES scalars and each output beat
// OUT_LANES scalars, lane 0 in the least significant bits.
module tb;
{dut_parameters}  localparam integer IN_LANES = {in_lanes};{lanes_note["IN_LANES"]}
  localparam integer OUT_LANES = {out_lanes};{lanes_note["OUT_LANES"]}
  localparam integer IN_W        = IN_LANES * {in_width};
  localparam integer OUT_W       = OUT_LANES * {out_width};
  localparam integer IN_BEATS    = {in_beats};
  localparam integer OUT_BEATS   = {out_beats};
  localparam integer ACLK_PS     = {aclk_ps};
  localparam integer BEAT_PS     = {beat_ps};
  localparam integer FIFO_LIMIT  = {fifo_limit};
  localparam integer DRAIN_STALL = {drain_stall};
  localparam integer IDLE_LIMIT  = {idle_limit};

  reg aclk = 0;
  always #(ACLK_PS / 2) aclk = ~aclk;
  reg aresetn = 0;

  reg [IN_W-1:0] stimulus [0:IN_BEATS-1];

  reg              s_axis_tvalid = 0;
  reg  [IN_W-1:0]  s_axis_tdata  = 0;
  wire             s_axis_tready;
  wire             m_axis_tvalid;
  wire [OUT_W-1:0] m_axis_tdata;
  reg              m_axis_tready = 0;

  {top} {"#(" + overrides + ") " if overrides else ""}dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tdata(s_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .m_axis_tdata(m_axis_tdata));

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

  // Receive-clock source and clock-domain-crossing buffer. A radio front end
  // delivers one beat every BEAT_PS and never pauses, so beat k has arrived
  // once simulation time reaches stream_start + k*BEAT_PS. The crossing FIFO
  // occupancy is the number of beats that arrived but were not yet accepted.
  integer arrived = 0, sent = 0, level = 0, fifo_peak = 0;
  reg     fifo_overflow = 0;
  integer next_sent, next_arrived;
  time    produced;

  always @(posedge aclk) begin
    if (!aresetn) begin
      arrived <= 0; sent <= 0; level <= 0;
      s_axis_tvalid <= 0; s_axis_tdata <= 0;
    end else begin
      next_sent = sent;
      if (s_axis_tvalid && s_axis_tready) begin
        $fwrite(in_file, "%0d %0d\\n", sent, cycle);
        next_sent = sent + 1;
      end
      if (BEAT_PS == 0) next_arrived = IN_BEATS;
      else begin
        produced = ($time - stream_start) / BEAT_PS + 1;
        next_arrived = (produced > IN_BEATS) ? IN_BEATS : produced;
      end
      level = next_arrived - next_sent;
      if (level > fifo_peak) fifo_peak <= level;
      if (FIFO_LIMIT > 0 && level > FIFO_LIMIT) fifo_overflow <= 1;
      // AXI4-Stream forbids withdrawing or altering an offered beat.
      if (!(s_axis_tvalid && !s_axis_tready)) begin
        if (next_sent < IN_BEATS && level > 0) begin
          s_axis_tvalid <= 1;
          s_axis_tdata  <= stimulus[next_sent];
        end else
          s_axis_tvalid <= 0;
      end
      arrived <= next_arrived;
      sent    <= next_sent;
    end
  end

  // Output sink: drains continuously, optionally applying random backpressure.
  integer received = 0, stalls = 0;
  integer unsigned roll;
  reg              held_valid = 0, held_ready = 0;
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
        if (m_axis_tdata !== held_data)
          $fatal(1, "M_AXIS payload changed while backpressured at cycle %0d", cycle);
      end
      if (m_axis_tvalid && m_axis_tready) begin
        $fwrite(out_file, "%0d %0d %h\\n", received, cycle, m_axis_tdata);
        received <= received + 1;
      end else if (m_axis_tvalid && !m_axis_tready)
        stalls <= stalls + 1;
      held_valid <= m_axis_tvalid; held_ready <= m_axis_tready;
      held_data  <= m_axis_tdata;
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
      $fatal(1, "no AXI handshake for %0d cycles after %0d of %0d input beats and %0d of %0d output beats",
             IDLE_LIMIT, sent, IN_BEATS, received, OUT_BEATS);
    if (received >= OUT_BEATS && (OUT_BEATS > 0 || sent == IN_BEATS)) begin
      $display("SUMMARY cycles=%0d fifo_peak=%0d fifo_overflow=%0d stalls=%0d",
               cycle, fifo_peak, fifo_overflow, stalls);
      $fclose(in_file); $fclose(out_file);
      $finish;
    end
  end
endmodule
"""


def beats(scalars: np.ndarray, lanes: int, fmt: tuple[int, int, bool]) -> list[str]:
    """Pack scalars `lanes` per beat; a final partial beat is zero-filled."""
    q = quantize_format(scalars, fmt)
    q = np.concatenate([q, np.zeros(-len(q) % lanes, dtype=object)])
    return [pack_hex(q[i:i + lanes], fmt[0]) for i in range(0, len(q), lanes)]


def lane_count(parameters: dict[str, str], name: str, default: int) -> int:
    """The RTL's own choice of scalars per beat (an integer default), else `default`."""
    text = parameters.get(name)
    if text is None:
        return default
    try:
        value = int(text, 0)
    except ValueError:
        raise ValueError(f"top-module parameter {name} must default to an integer literal, not {text!r}")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def read_log(path: Path, columns: int) -> list[list[str]]:
    rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    if any(len(row) != columns for row in rows):
        raise RuntimeError(f"{path.name} is malformed")
    return rows


def due(stream: Stream, samples: int) -> int:
    """How many expected output scalars are determined by the first `samples` inputs."""
    count = int(np.count_nonzero(stream.ready <= samples))
    if np.any(stream.ready[:count] > samples):
        raise ValueError("expected output must be ordered by when it is determined (ready)")
    return count


def budget(params: dict, stream: Stream) -> float | None:
    """Target clock cycles per input sample, if the project sets a rate."""
    target = params.get("target") or {}
    if target.get("frequency") and target.get("sample_rate"):
        return float(target["frequency"]) / float(target["sample_rate"])
    if target.get("cycles") and stream.frame:
        return float(target["cycles"]) / stream.frame
    return None


def generate(args: argparse.Namespace) -> int:
    """Write the input and expected output streams, without RTL.

    input.hex/output.hex hold one sample / one output element per line, packed
    as the testbench would (lane 0 least significant, scaled by 2**FRAC).
    input.txt/output.txt hold the same values unscaled; ready.txt holds, per
    output element, how many input samples determine it.
    """
    project_dir = args.generate.resolve()
    reference = project_dir / "main.py"
    if not reference.is_file():
        raise ValueError(f"project entry point does not exist: {reference}")
    params = load_params(reference)
    samples = args.samples or default_samples(params)
    stream = load_stream(load_reference(reference, params), params, samples,
                         np.random.default_rng(args.seed))
    work = (args.io or project_dir / "IO").resolve()
    work.mkdir(parents=True, exist_ok=True)
    count = due(stream, samples)
    for name, values, lanes, fmt in (("input", stream.x, stream.in_lanes, stream.in_format),
                                     ("output", stream.y[:count], stream.out_lanes, stream.out_format)):
        (work / f"{name}.hex").write_text("".join(f"{b}\n" for b in beats(values, lanes, fmt)))
        rows = np.asarray(values, dtype=float).reshape(-1, lanes)
        (work / f"{name}.txt").write_text("".join(" ".join(f"{v:.10g}" for v in row) + "\n" for row in rows))
    (work / "ready.txt").write_text("".join(f"{r}\n" for r in stream.ready[:count:stream.out_lanes]))
    print(f"{stream.samples} input samples ({samples} measured), {count // stream.out_lanes} output "
          f"elements; input {stream.in_format}, output {stream.out_format} (bits, frac, signed): {work}")
    return 0


def main() -> int:
    evaluation_started = time.perf_counter()
    args = arguments()
    if args.generate is not None:
        return generate(args)
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
    if not 0 <= args.drain_stall < 100:
        raise ValueError("--drain-stall must be a percentage below 100")
    params = load_params(reference)
    samples = args.samples or default_samples(params)
    # Record the seed so the Python reference for this exact stimulus can be regenerated.
    seed = args.seed if args.seed is not None else int(np.random.SeedSequence().entropy % 2**63)
    module = load_reference(reference, params)
    stream = load_stream(module, params, samples, np.random.default_rng(seed))
    samples = min(samples, stream.samples)
    expected = due(stream, samples)

    rtl_dir = conversion_dir / "rtl"
    files = verilog_files(rtl_dir)
    top = infer_top(files, args.top)
    declared = top_parameters(files, top)
    # Framed projects keep the historical one-sample-per-beat interface.
    in_lanes = stream.in_lanes if stream.frame else lane_count(declared, "IN_LANES", stream.in_lanes)
    out_lanes = stream.out_lanes if stream.frame else lane_count(declared, "OUT_LANES", stream.out_lanes)
    (in_width, in_frac, _), (out_width, out_frac, _) = stream.in_format, stream.out_format
    values = dict(WIDTH=in_width, FRAC=in_frac, N=stream.frame or 0, IN_WIDTH=in_width,
                  IN_FRAC=in_frac, OUT_WIDTH=out_width, OUT_FRAC=out_frac,
                  IN_LANES=in_lanes, OUT_LANES=out_lanes)
    supplied = {name: values[name] for name in (*SUPPLIED, "IN_LANES", "OUT_LANES")
                if name in declared and not (name == "N" and not stream.frame)}

    target = params.get("target") or {}
    aclk_ps = DEFAULT_ACLK_PS
    if target.get("frequency"):
        aclk_ps = max(2, 2 * round(5e11 / float(target["frequency"])))
    samples_per_beat = in_lanes / stream.in_lanes
    beat_ps = 0
    if args.rate > 0:
        beat_ps = round(1e12 * samples_per_beat / args.rate)
        if beat_ps <= aclk_ps // 2:
            raise ValueError(f"input rate {args.rate:g} samples/s is faster than one beat per aclk cycle")

    work = (args.io or conversion_dir / "IO").resolve()
    work.mkdir(parents=True, exist_ok=True)
    for asset in rtl_dir.iterdir():
        if asset.is_file() and asset.suffix.lower() in {".hex", ".mif", ".mem"}:
            shutil.copy2(asset, work / asset.name)
    stimulus = beats(stream.x, in_lanes, stream.in_format)
    (work / "vectors.hex").write_text("\n".join(stimulus) + "\n")
    out_beats = math.ceil(expected / out_lanes)
    reference = stream.y[:expected]
    # Both sides of the comparison, in real units, one entry per output scalar.
    group_of = np.empty(expected, dtype=object)
    for name, mask in stream.groups.items():
        group_of[mask[:expected]] = name

    def save_outputs(received: np.ndarray) -> None:
        """Write the Python reference beside whatever the RTL has produced so far
        (NaN where it produced nothing), so a run that dies still shows its prefix."""
        actual = np.full(expected, np.nan)
        actual[:len(received)] = received
        errors = actual - reference
        np.savez_compressed(work / "outputs.npz", x=stream.x, expected=reference, actual=actual,
                            error=errors, ready=stream.ready[:expected], group=group_of.astype(str),
                            received=len(received), in_format=np.array(stream.in_format, dtype=int),
                            out_format=np.array(stream.out_format, dtype=int),
                            in_lanes=stream.in_lanes, out_lanes=stream.out_lanes, seed=seed)
        # "-" marks values the RTL has not produced (yet).
        (work / "outputs.txt").write_text(
            "# index group expected(python) actual(rtl)\n"
            + "".join(f"{i} {g} {e:.10g} {'-' if i >= len(received) else f'{a:.10g}'}\n"
                      for i, (g, e, a) in enumerate(zip(group_of, reference, actual))))

    save_outputs(np.array([]))
    tb = work / "tb.sv"
    fifo_limit = args.fifo if beat_ps else 0
    tb.write_text(make_tb(top, supplied, in_lanes, out_lanes, in_width, out_width, len(stimulus),
                          out_beats, aclk_ps, beat_ps, fifo_limit, args.drain_stall, args.timeout))
    for stale in ("input.log", "output.log"):
        (work / stale).unlink(missing_ok=True)
    if args.simulator == "iverilog":
        subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o",
                        str(work / "sim.vvp"), str(tb), *map(str, files)], check=True, cwd=work)
        run_cmd = ["vvp", str(work / "sim.vvp")]
    else:
        # Jailed: the RTL is the agent's, and xsim runs it on the host.
        sources = [str(tb), *map(str, files)]
        readable = sorted({Path(f).resolve().parent for f in files} - {work})
        built = subprocess.run(xilinx.command(
            f"xvlog -sv {shlex.join(sources)} && xelab -debug off -s vrp_tb tb",
            work, [work], readable), cwd=work, text=True, capture_output=True)
        if built.returncode:
            print(built.stdout + built.stderr, end="", file=sys.stderr)
            raise RuntimeError("xsim compilation failed")
        run_cmd = xilinx.command("xsim vrp_tb -R", work, [work], readable)

    def received_outputs() -> tuple[list, np.ndarray]:
        rows = read_log(work / "output.log", 3) if (work / "output.log").exists() else []
        return rows, np.array([v for row in rows[:out_beats]
                               for v in unpack(row[2], out_lanes, stream.out_format)])[:expected]

    try:
        run = subprocess.run(run_cmd, cwd=work, text=True, capture_output=True)
    except KeyboardInterrupt:
        # Keep what the RTL produced before the interrupt; a beat cut mid-line is dropped.
        lines = (work / "output.log").read_text().splitlines(True) if (work / "output.log").exists() else []
        complete = "".join(line for line in lines if line.endswith("\n") and len(line.split()) == 3)
        (work / "output.log").write_text(complete)
        save_outputs(received_outputs()[1])
        raise

    summary = {}
    for line in run.stdout.splitlines():
        if line.startswith("SUMMARY "):
            summary = dict(field.split("=", 1) for field in line.split()[1:])
    outputs, actual = received_outputs()
    save_outputs(actual)
    if len(outputs) < out_beats or not summary:
        print(run.stdout, end="", file=sys.stderr)
        print(run.stderr, end="", file=sys.stderr)
        wrong = np.flatnonzero(actual != reference[:len(actual)])
        print(f"received {len(actual)} of {expected} output values; {len(wrong)} differ from the "
              f"reference" + (f", first at {wrong[0]}" if len(wrong) else "")
              + f"; python and rtl outputs: {work / 'outputs.txt'}", file=sys.stderr)
        raise RuntimeError(f"simulation produced {len(outputs)} of {out_beats} output beats")
    accepted = read_log(work / "input.log", 2)

    measurements = measure(stream, actual, expected)
    primary = stream.primary
    rmse = measurements[primary]["rmse"]
    precision = measurements[primary]["precision_bits"]
    errors = actual - reference
    worst = np.argsort(-np.abs(errors))[:12]
    project_generate = getattr(module, "generate", None)
    reproducible = (not callable(project_generate)
                    or "rng" in inspect.signature(project_generate).parameters)
    (work / "errors.json").write_text(json.dumps({
        "seed": seed,
        # False when the project's generate() draws from its own unseeded RNG.
        "seed_reproduces_stimulus": reproducible,
        "primary": primary,
        "measurements": {name: {**v, "precision_bits": v["precision_bits"]
                                if v["precision_bits"] is not None and np.isfinite(v["precision_bits"]) else None,
                                "exact": bool(v["samples"] and v["mismatches"] == 0)}
                         for name, v in measurements.items()},
        "rmse": rmse,
        "worst": [{"output_scalar": int(i), "element": int(i) // stream.out_lanes,
                   "lane": int(i) % stream.out_lanes, "ready_after_samples": int(stream.ready[i]),
                   "expected": float(stream.y[i]), "actual": float(actual[i]), "error": float(errors[i])}
                  for i in worst]}, indent=2) + "\n")

    # Throughput over the measured input; latency from the input beat that
    # completes each output beat's data to that output beat.
    in_cycles = np.array([int(row[1]) for row in accepted])
    cut_beats = min(len(in_cycles), math.ceil(samples * stream.in_lanes / in_lanes))
    throughput = ((in_cycles[cut_beats - 1] - in_cycles[0]) / ((cut_beats - 1) * samples_per_beat)
                  if cut_beats > 1 else float("nan"))
    latency = 0
    for j, row in enumerate(outputs[:out_beats]):
        last = min((j + 1) * out_lanes, expected) - 1
        needed = (int(stream.ready[last]) * stream.in_lanes - 1) // in_lanes
        if needed < len(in_cycles):
            latency = max(latency, int(row[1]) - int(in_cycles[needed]))
    fifo_peak = int(summary.get("fifo_peak", 0))
    overflowed = summary.get("fifo_overflow", "0") != "0"

    print(f"evaluation time: {time.perf_counter() - evaluation_started:.1f}s")
    print(f"simulator: {args.simulator}")
    print(f"input rate: {'unthrottled' if not beat_ps else f'{args.rate / 1e6:.4g} MS/s'}")
    print(f"stream: {samples} input samples measured ({stream.samples} sent), {expected} output values; "
          f"IN_LANES={in_lanes}, OUT_LANES={out_lanes}")
    print(f"formats (bits, frac, signed): input {stream.in_format}, output {stream.out_format}")
    print(f"throughput: {throughput:.4g} cycles/sample")
    print(f"latency: {latency} cycles")
    if beat_ps:
        print(f"crossing FIFO: {fifo_peak} beats" + (f" of {fifo_limit}" if fifo_limit else "")
              + (" OVERFLOW" if overflowed else ""))
    print(f"measurement group: {primary}")
    if precision is not None:
        print(f"bits of precision: {precision:.9g}")
        print(f"RMS error: {rmse:.9g}")
    else:
        print("bits of precision: unavailable (no reference samples)")
        print("RMS error: unavailable (no reference samples)")
    for name, v in measurements.items():
        print(f"output group {name}: {v['mismatches']} mismatches / {v['samples']} samples; RMSE={v['rmse']}")
    print(f"numerical diagnostics: {work / 'errors.json'}")
    print(f"python and rtl outputs: {work / 'outputs.txt'}, {work / 'outputs.npz'} (seed {seed})")
    for i in worst[:3]:
        print(f"  output value {i} (element {i // stream.out_lanes}, lane {i % stream.out_lanes}): "
              f"expected {stream.y[i]:.8g}, got {actual[i]:.8g}, error {errors[i]:.8g}")
    if (cycles := budget(params, stream)) is not None:
        print(f"cycle target: {cycles:.4g} cycles/sample; measured/target: {throughput / cycles:.9g}")
    # Exit status is about measurement validity, never a performance threshold.
    return 1 if run.returncode != 0 else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"sim.py: {error}", file=sys.stderr)
        raise SystemExit(1)
