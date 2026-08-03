# Python → SystemVerilog (first draft)

Convert the **Translation Target Function** in the attached Python into synthesizable
SystemVerilog implementing a clocked FSM, using fixed-point arithmetic per `params.yaml`.

## Deliverables — emit exactly these two files using markers:

```
=== FILE: hls/kernel.h.sv ===
...
=== FILE: hls/kernel.sv ===
```

No markdown fences. No commentary outside the file blocks. Do NOT emit tb.sv (generated automatically).

`kernel.h.sv` holds `` `define ``/typedef-equivalent width constants shared with the testbench
generator (see below); `kernel.sv` holds the `kernel_top` module implementation. Both are compiled
together — you may also just put everything in `kernel.sv` and leave `kernel.h.sv` emitting only
the shared width defines used by dimension macros below.

## Naming convention (tb.sv is generated automatically — follow this exactly)

Inputs and outputs are numbered by their order in `manifest.json` (inputs separately from outputs,
both 0-indexed). Use these names verbatim:

- Input ports:      `in0`, `in1`, ... (flat `signed [W-1:0]` buses; arrays are flattened, indexed
  by the same per-dimension macros as below — element `[i0][i1]` lives at bit offset
  `(i0*DIM_IN{N}_1 + i1) * W`, low-to-high, matching row-major C order)
- Output ports:     `out0`, `out1`, ...
- Dimension macros: `` `define DIM_IN{N}_{d} <size> `` / `` `define DIM_OUT{N}_{d} <size> ``
  (only for non-scalar tensors), placed in `kernel.h.sv`.
- Complex tensors: two consecutive fields per element, real then imaginary, each of the
  component width — i.e. a complex array's flat bus is twice as wide as a same-shape real array,
  with `.re`/`.im` interleaved per element in the flattened bit vector.
- Module name: `kernel_top`, defined in `kernel.sv`.

## Fixed-point convention

There is no `ap_fixed` in plain SystemVerilog. Every input/output port is a plain two's-complement
integer bit vector. **Port width = `bits + signed`** from that tensor's `params.yaml` entry — this
matches the HLS-path convention (`ap_fixed<bits+signed, ...>`) and is exactly what the
auto-generated testbench (`gen_tb_v.py`) computes, so getting this formula wrong means every port
on your module mismatches the testbench and iverilog will warn/truncate silently. Worked example:
`bits: 16, signed: 1` → port width **17**, declared `input wire signed [16:0] in0` (NOT `[15:0]`).
`bits: 16, signed: 0` → port width **16**, declared `input wire [15:0] in0`.

The **fraction** field in `params.yaml` is a separate convention — it tells the testbench how many
low bits represent the fractional part when converting to/from the floating-point reference
values; it has no effect on port width. Internally:

- Treat every port as a plain two's-complement integer of the declared width.
- Do all arithmetic in fixed-point integer form (shift instead of divide by powers of two,
  widen intermediate registers to avoid overflow, then truncate/round back down before writing
  an output port).
- **No `real`/floating-point types anywhere** — this defeats the purpose of hardware synthesis.

## Module interface (mandatory — the auto-generated testbench depends on this exactly)

```systemverilog
module kernel_top (
    input  wire clk,
    input  wire rst,     // per params.yaml reset.active_level / reset.sync
    input  wire start,   // pulsed one cycle by the testbench to begin a run
    output reg  busy,    // high while computing; the testbench counts clock
                          // cycles only while busy is high — this is not
                          // decorative, it IS the reported clock_cycles metric
    output reg  done,     // pulsed exactly one cycle when outputs are valid
    input  wire [...] in0, ...,
    output reg  [...] out0, ...
);
```

- On `rst`, clear `busy`/`done` and return to idle.
- On `start` (while idle), latch inputs, assert `busy`, and begin computing.
- When the result is ready, assert `done` for exactly one clock, deassert `busy`, and return to
  idle. Outputs must be valid and stable starting the cycle `done` is asserted.
- **`busy` must be asserted for at least one full clock cycle on every run, with no exceptions —
  even a design whose result is ready combinationally the same cycle `start` arrives must still
  hold `busy` high for that one cycle before pulsing `done`.** A design that never asserts `busy`
  (e.g. driving `done` directly off `start` while leaving `busy` tied to 0) is not a "zero-cycle"
  design — it is broken, because it reports a cycle count of 0 for a computation that still took a
  real clock edge to happen. If your logic is purely combinational, keep the mandatory FSM handoff
  cycle anyway: `start` → assert `busy` this cycle, latch the combinational result → next cycle,
  pulse `done`, deassert `busy`. This costs one honest cycle and cannot be optimized away.
- Do not assert `busy` and `done` simultaneously on the same edge beyond that one handoff cycle.
- Every clock edge spent with `busy` high counts toward `clock_cycles` — so the number of cycles
  between `start` and `done` is a direct, real measurement of your design's latency. There is no
  way to fake this number; it comes from the testbench's own counter, not from anything you write.
  Removing or bypassing the `busy` assertion to make `clock_cycles` read lower is a correctness
  bug, not an optimization — it will be treated as a failing design.

## Requirements

- Match the Python function's inputs/outputs (names, arity, shapes) using fixed-point widths
  derived from `params.yaml` exactly as described above.
- Kernel: synthesizable SystemVerilog-2012 subset (no `initial` blocks driving outputs, no
  `#delay` statements inside `kernel.sv`, no `real`/`string` types, no recursive/dynamic
  constructs) — this must be able to run through `iverilog -g2012` and, later, real synthesis.
- Use a clear FSM (explicit state register) rather than deeply nested combinational logic for
  multi-step algorithms (loops, iterative convergence, etc.) — each FSM state transition should
  correspond to genuine clocked latency, not be an artifact of how you happened to write the loop.
- **State register width**: declare the state register as `[$clog2(NUM_STATES)-1:0]`, and give
  every state constant a size specifier wide enough for the largest state number — e.g. with 36
  states use `[5:0]` and `6'd0` .. `6'd35`, not `[4:0]`/`5'd`. A literal's own size specifier
  truncates at parse time regardless of the register it's assigned to, so a state numbered ≥32
  written as `5'd32` silently becomes `0` and the FSM will jump to the wrong state or hang. Count
  your states before picking the width, don't guess.

When both files are complete, stop.
