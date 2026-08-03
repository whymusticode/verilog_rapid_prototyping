# Area estimation with Yosys — validation + speed comparison

Prompted by: wanting real area numbers (LUT/gate/FF counts) instead of just
`clock_cycles`. iverilog is confirmed simulation-only (no synthesis at all —
no `-t area`, no netlist/utilization output). Yosys is a real open-source
synthesis tool and can give technology-independent cell counts.

## 1. Ground-truth sanity check: does Yosys's area number mean anything?

`one_adder.v` (one 16-bit adder) vs `two_adder.v` (two independent 16-bit
adders — deliberately unrelated so nothing can be shared/folded):

```
$ yosys -p "read_verilog one_adder.v; synth -top one_adder; stat"
Number of cells: 98

$ yosys -p "read_verilog two_adder.v; synth -top two_adder; stat"
Number of cells: 196
```

**Exactly 2x** — confirms `stat`'s cell count is a real, trustworthy relative
area metric, not noise. Safe to use for round-over-round optimizer comparisons
(e.g. "did this change actually shrink the design or just move logic around").

## 2. Can Yosys's frontend handle real generated kernels?

- `dot4`'s `kernel.sv` (the small mid-size project from earlier in this
  session): synthesizes cleanly, 8484 cells.
- The real `eig_10` kernel (`kernel_bench.sv`, 36-state FSM, 512-entry sin/cos
  ROM via `initial`-block integer recurrence, dense fixed-point matrix
  arithmetic): **also synthesizes cleanly**, 208,100 cells, ~137s CPU / ~2GB
  peak memory. No errors on any of the constructs the LLM used.

**Caveat found**: Yosys's frontend does NOT accept the auto-generated
testbenches (`tb.sv` / `bench_tb.sv`) as-is — they use `real rv, iv;` for
fixed-point↔float file I/O conversion, and `real` isn't synthesizable, so
Yosys's parser rejects it (`ERROR: syntax error, unexpected TOK_REAL`). This
is expected and correct: those testbenches were never meant to be
synthesized. For both the area check and the sim-speed comparison below,
a separate `_stim.sv` wrapper was written that drives the same input values
without `real`/file I/O — Yosys's `sim -clock -reset` drives clk/rst itself,
so the stimulus only needs to supply `start` and constant input values.

## 3. Does Yosys have a simulator, and is it faster than iverilog?

Yes — `yosys sim -clock clk -reset rst -n N` simulates the **synthesized
gate-level netlist** (not the RTL directly, unlike iverilog/xsim). Tested
against the same dense-matrix, non-converging `eig_10` workload as
`PoC/vivado_vs_iverilog/eig10/bench_tb.sv`, same 200,000-cycle budget:

| Simulator            | What it simulates      | Prep/elaborate (one-time) | Sim time (200k cycles) |
|-----------------------|------------------------|---------------------------|--------------------------|
| iverilog (`vvp`)      | RTL, interpreted       | ~0s (no separate step)    | 0.43s                   |
| xsim (Vivado)         | RTL, native-compiled   | not free, excluded above  | 2.65s wall (0.67s reported kernel time) |
| **yosys `sim`**        | **gate-level netlist**  | ~66-91s (`synth`/`prep`)  | **~24s**                |

**Yosys's `sim` is roughly 55x slower than iverilog** for this workload, and
its one-time synthesis/prep cost alone (~70-90s) already exceeds iverilog's
entire run. This isn't a knock on Yosys — it's simulating actual synthesized
gates (muxes, individual `$_AND_`/`$_XOR_` primitives etc.), which is a much
finer-grained, slower simulation than an RTL behavioral simulator interpreting
`always @(posedge clk)` blocks directly. Yosys's `sim` is a verification tool
for confirming synthesis didn't change behavior (equivalence-style checking),
not a fast functional simulator — using it as the primary simulation backend
for this pipeline would be strictly worse than iverilog on every axis (speed,
testbench compatibility) with no upside.

## Conclusion / recommended integration

- **Use Yosys for area only** (`synth` + `stat`), not as a simulation backend
  — iverilog remains the right tool for functional correctness + clock_cycles
  (per `PoC/vivado_vs_iverilog/README.md`).
- **Generic technology-independent synthesis** (`synth -top kernel_top`, not
  `synth_xilinx`) — confirmed it handles real generated kernels including the
  hardest one tried so far (`eig_10`'s 36-state FSM + ROM).
- Area numbers need a **kernel.sv-only synth pass** (LLM's file, no
  testbench) — this already works with no wrapper needed, since `kernel.sv`
  itself never uses `real`.
- Not yet wired into `convert.py`/`optimize.py` — this directory only
  validates the approach. Next step (separate task): add `synth -top
  kernel_top; stat -json` as an optional step, add its cell/mux/DFF counts to
  `summary.json` alongside `clock_cycles`, decide whether the optimizer prompt
  should ever target area (right now `optimize_verilog.md` explicitly only
  covers cycle-relevant techniques since nothing measured area — that
  reasoning updates once this lands for real).

## Reproduce

```
# ground truth 2x check
yosys -p "read_verilog one_adder.v; synth -top one_adder; stat"
yosys -p "read_verilog two_adder.v; synth -top two_adder; stat"

# area on a real kernel (no wrapper needed -- kernel.sv has no `real`)
yosys -p "read_verilog -sv kernel.h.sv kernel.sv; synth -top kernel_top; stat"

# sim speed comparison (needs the *_stim.sv wrapper, ~70-90s prep step)
yosys -p "read_verilog -sv eig10_kernel.h.sv eig10_kernel.sv eig10_stim.sv; prep -top stim_top; sim -clock clk -reset rst -n 200000"
```
