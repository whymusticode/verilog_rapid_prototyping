# iverilog vs Vivado Simulator (xsim) — wall-clock comparison

Prompted by: the real `eig_10` conversion (conversion_027, full 10x10 complex Jacobi
eigendecomposition, `max_iter=2000`) never finished under iverilog within a 300s
timeout. Question: is Vivado's simulator meaningfully faster for this class of design?

## Setup

- `eig10/kernel.sv` — the actual LLM-generated kernel from conversion_027, with one
  real bug fixed: the FSM has 36 states (`S_IDLE`=0 .. `S_DONE_ST`=35) but the state
  register and every state literal were declared 5 bits wide (`reg [4:0] state`,
  `5'd32` etc.) — Verilog literal size-specifiers truncate at parse time regardless of
  the target register's width, so states 32-35 silently aliased to states 0-3 and the
  FSM could never reach `S_DONE_ST`. Fixed by widening to `[5:0]`/`6'd`. This bug alone
  fully explained the original "hang" — it was not a scale/performance problem, it was
  a correctness bug that happened to look like an infinite loop.
- `eig10/kernel_bench.sv` — the fixed kernel with `THRESH` patched to an unreachable
  negative value, so the pivot-search convergence check never exits early. Needed
  because the natural test matrix converges (or the kernel's matrix-update zeroes out
  more than intended — a second, separate bug not chased down here) within 1-2 sweeps,
  which makes the FSM go idle almost immediately and any wall-clock comparison mostly
  measures per-invocation overhead instead of sustained simulation throughput.
- `eig10/bench_tb.sv` — drives a dense, all-off-diagonals-nonzero 10x10 matrix and runs
  a fixed `N_CYCLES` (never waits for `done`), so both simulators do byte-for-byte
  identical work and their results (`iter_z`, `state`, etc. at the end) can be diffed
  for correctness parity before comparing speed.

## Results

Both simulators produced **bit-identical results** at every cycle count tested
(`iter_z=28, state=16` at 200k cycles; `iter_z=140, state=16` at 1M cycles) — confirms
this isn't a simulator-semantics difference, just a speed comparison.

| N_CYCLES  | iverilog (`vvp`) wall-clock | xsim wall-clock | xsim reported kernel time |
|-----------|------------------------------|------------------|---------------------------|
| 200,000   | 0.43s                        | 2.65s            | 0.67s                     |
| 1,000,000 | 2.18s                        | 2.92s            | 0.95s                     |

Takeaways:
- **xsim has a large, mostly-fixed per-invocation overhead (~2s)** — session startup,
  license check, TCL sourcing — separate from the one-time `xvlog`/`xelab`
  compile/elaborate step (also not free, and also excluded from the table above).
- **iverilog has effectively no such overhead** — wall-clock is almost entirely actual
  simulation work.
- **Marginal (per-cycle) cost**: going from 200k→1M cycles (5x), iverilog's time scaled
  ~5x (linear, as expected for an interpreted simulator). xsim's *reported kernel time*
  only grew 0.67s→0.95s — its native-compiled core is genuinely faster per cycle once
  running, but the fixed overhead dominates at these cycle counts.
- **Crossover**: extrapolating marginal cost (iverilog ≈2.2µs/1k cycles, xsim's kernel
  ≈0.35µs/1k cycles marginal), xsim's compiled-code speed advantage would only start
  winning on wall-clock past roughly 15-20M cycles — well beyond what's needed for a
  single Jacobi sweep or even a few hundred sweeps of this design.

## Conclusion

For the cycle counts this pipeline actually needs (thousands to low millions of
cycles per conversion run), **iverilog is the better choice** — xsim's per-cycle
speed advantage doesn't overcome its startup tax at this scale, and iverilog requires
no Vivado license/install at all. The original `eig_10` "hang" was a real correctness
bug (state-width overflow), not evidence that iverilog is too slow for this class of
design — once fixed, one Jacobi sweep completes in well under a second either way.

The actual scale problem — `max_iter=2000` full sweeps taking minutes even after the
bug fix — is a genuine simulation-time concern for *both* simulators (xsim would also
take proportionally long once its fixed overhead is amortized), which is the reason
[eig_10_1iter](../../projects/eig_10_1iter/) exists: validate correctness on 1 real
sweep before ever attempting to simulate a full 2000-sweep convergence run.

## Reproduce

```
./run_bench.sh [N_CYCLES]   # default 200000
```

Requires iverilog and a local Vivado 2025.2 install (`~/Xilinx/2025.2/Vivado`).
