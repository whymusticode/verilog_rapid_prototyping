# Automated Bit-Width Optimization: State of the Art

Context: we start from Python code, match it to Verilog, then place & route for
a target FPGA. A key lever for minimizing LUT usage (and power, Fmax, routing
congestion) is choosing the *smallest* bit-widths that still meet accuracy.
This is known variously as **word-length optimization (WLO)**, **bit-width
allocation**, or **precision tuning**.

---

## 1. The theoretical framing

Fixed-point WLO is classically split into two sub-problems:

1. **Range analysis → Integer Word Length (IWL).**
   For each signal, find the smallest number of integer bits that avoids
   overflow across all reachable inputs. This is a *sound* analysis: you need
   an over-approximation of the value range.

2. **Precision analysis → Fractional Word Length (FWL).**
   Given IWLs are fixed, pick fractional bits per signal to meet an
   application-level error budget (MSE, max-abs-error, SQNR, classification
   accuracy, ...) while minimizing hardware cost (LUTs, DSPs, area, energy).

Total width = IWL + FWL (+ sign bit). The signal-by-signal vector of widths
is the decision variable; the cost function is a hardware model; the
constraint is an error bound. That's a constrained combinatorial
optimization problem — and in general **NP-hard** (the feasible space grows
exponentially in the number of signals, and the cost/error surfaces are
non-convex and non-separable because of signal interactions).

So there is no single closed-form "theory of optimal bit-width." What exists
is a toolbox of analyses + search strategies with well-understood tradeoffs.

---

## 2. Range analysis techniques

Ordered roughly from loosest → tightest (and cheapest → most expensive):

| Method | Idea | Pros | Cons |
|---|---|---|---|
| **Interval arithmetic (IA)** | Track `[lo, hi]` per signal | Trivial, fast | Ignores correlation between operands → blow-up on feedback loops |
| **Affine arithmetic (AA)** | Each signal = central value + sum of noise symbols; correlated operands share symbols | Much tighter than IA on dataflow with reconvergence; handles linear ops exactly | Non-linear ops (mul, div, non-linear functions) require Chebyshev approximations; symbol count grows |
| **Satisfiability Modulo Theories (SMT)** | Ask an SMT solver for exact reachable range | Exact on bounded programs | Doesn't scale past small kernels |
| **Simulation / profiling** | Run representative inputs, take empirical min/max (+ margin) | Scales to large designs; captures real distribution | *Unsound* — an unseen input can overflow |
| **Abstract interpretation / polyhedral** | Track polyhedra or zonotopes through the program | Tight on loops and linear flows | Implementation complexity |

**Current practice:** hybrid. Affine arithmetic for the analytical backbone,
simulation for validation and to pick the margin, SMT for targeted hot spots.

Key paper: *Fang, Rutenbar, Chen — Enhanced Precision Analysis for
Accuracy-Aware Bit-Width Optimization Using Affine Arithmetic* (IEEE TCAD).
Shows AA-based analysis reducing fractional bit-width >35% vs prior static
analyses.

---

## 3. Precision / FWL search strategies

Given a cost model and an error bound, how do you pick per-signal FWLs?

- **Uniform word-length (UWL):** one FWL for everybody. Cheap to search (1D),
  universally suboptimal — pays worst-case bits everywhere.
- **Max-1 / gradient descent (Sung & Kum, the classic baseline):** start
  high, reduce each signal's bits one at a time while error stays in budget.
  Works, but slow — `O(N × simulations)` and greedy.
- **Analytical MSE models** (Constantinides et al.): propagate rounding
  noise as a random process through the DFG, get a closed-form MSE as a
  function of the width vector, then do integer linear programming or
  convex relaxation. Fast, but assumes LTI-ish behavior and small noise.
- **GRASP / simulated annealing / genetic search:** stochastic local
  search; good empirical results, reported ~17–22% cost reduction over IA
  baselines and up to ~600× faster than classical max-1.
- **Gradient-based / differentiable precision (the modern wave):** treat
  bit-width as a learnable parameter via straight-through estimators; jointly
  optimize with the model. Pervasive in ML-on-FPGA (QAT, mixed-precision
  quantization) — see e.g. *Single-Path Precision: Differentiable Bit-Width
  & Numeric-Format Learning for FPGA-Efficient Neural Networks* (2026).
- **ILP / MILP** with a linearized cost: gives optimality guarantees on
  small-to-medium designs; combines well with AA-derived error constraints.

---

## 4. Cost models (what "LUT usage" actually looks like to the optimizer)

Hardware cost is *not* linear in bit-width. Rules of thumb used in
WLO literature:

- **Adder / subtractor:** ~`W` LUTs (roughly linear), carry-chain dominated.
- **Multiplier:** ~`W_a × W_b / k` LUTs if LUT-based, or snaps to a DSP48
  block once operands fit (e.g. ≤18×25 on Xilinx 7-series / UltraScale).
  This **step function** at the DSP boundary is important — dropping a
  multiplicand from 19→18 bits can save a whole DSP.
- **Divider / sqrt / transcendentals:** super-linear; bit-width matters a
  lot. Often implemented via CORDIC or LUT + interpolation where FWL trades
  directly against ROM size.
- **Registers / pipeline:** linear in `W`, but affects routing and Fmax.
- **Memory (BRAM):** snaps to 18k/36k tiles; width changes may be free or
  may double BRAM count.

Modern flows estimate cost by **calling the synthesis tool in the loop**
(Vivado / Vitis HLS / Yosys + nextpnr) on candidate width vectors, often
with a surrogate ML model to avoid full re-synthesis every iteration.

---

## 5. What current tools actually do

- **Vitis HLS / Intel HLS:** `ap_fixed<W,I>` / `ac_fixed` types. User
  specifies widths manually; tool does *not* auto-optimize widths (it just
  synthesizes what you wrote). There are Xilinx tutorials for manual
  profile-driven tuning but no end-to-end auto-WLO in the shipped product.
- **MATLAB Fixed-Point Designer + HDL Coder:** closest mainstream
  "automatic" flow. Simulation-based range collection + proposed
  fraction lengths, with an optimization mode that searches for a cost
  minimum under tolerance — still sim-based, not sound.
- **Chisel / FIRRTL:** *forward* width inference from literals/ops. Not
  an optimizer — it just computes worst-case growing widths unless you cap
  them. `FixedPoint` (and newer `Interval`) types exist but WLO is your job.
- **Amaranth (nMigen):** shapes inferred from operations; widths grow
  conservatively (e.g. `a+b` → `max(w_a,w_b)+1`). No built-in WLO pass.
- **PyRTL:** automatic bit-width inference on unspecified wires; again
  growth-based, not optimization-based.
- **Research flows (Python → RTL with WLO):**
  - *Gappa* (INRIA) — formal error bounds for fixed-point / float kernels,
    often used as an oracle inside WLO loops.
  - *FloPoCo* — generates optimized arithmetic cores for arbitrary
    widths/precisions; excellent target for a WLO frontend.
  - *TrueFloat*, *HeteroCL*, *Allo*, *Dahlia* — HLS-adjacent DSLs that
    expose bit-width/precision as first-class knobs.
  - Differentiable-precision stacks built on PyTorch / JAX for ML models.

---

## 6. Practical recipe for this project (Python → Verilog → P&R)

A sensible staged pipeline to steal from the SOTA:

1. **Golden model in Python** using `numpy` (float64) as ground truth, plus
   a `fxpmath` / `softfloat` / `ap_fixed`-alike simulator for candidate
   fixed-point configs.
2. **Range discovery:**
   a. Affine arithmetic pass on the dataflow graph for sound IWLs.
   b. Monte-Carlo simulation across representative inputs to tighten and
      sanity-check. Flag any AA-predicted range that simulation never
      comes close to — likely an over-approximation to revisit.
3. **Initial FWL:** uniform, set from analytical noise model to hit the
   error budget + a safety margin.
4. **Local search (GRASP / simulated annealing):** per-signal FWL
   reduction, error checked by re-running the Python fixed-point simulator
   on a validation set.
5. **Cost oracle:** two tiers.
   - *Cheap:* analytical formula (LUTs per adder/mul, DSP snap points,
     BRAM granularity). Use inside the inner search loop.
   - *Expensive:* actual yosys/nextpnr (or Vivado) run on a shortlist of
     candidates. Use to pick the final width vector.
6. **Snap-to-DSP / BRAM awareness:** bias the search toward widths that
   fit native primitives — the cost curve is a staircase, not a ramp.
7. **Emit Verilog** with per-signal `[W-1:0]` widths from the final vector;
   keep the Python golden model and the fixed-point simulator as a
   regression harness.

Two big leverage points specific to "rapid prototyping":
- **Simulation-driven ranges with a wide margin** get you 80% of the win
  for 5% of the complexity; save AA/SMT for when something actually
  overflows or is clearly over-provisioned.
- **Let the DSP/BRAM staircase drive you, not the LUT ramp.** Saving a bit
  on an adder is a rounding error; saving one bit that removes a DSP is a
  double-digit-% area win.

---

## 7. Open problems / where the field is moving

- **Joint precision + scheduling + resource allocation.** Widths interact
  with loop tiling, pipeline II, and memory layout; recent frameworks
  (Prometheus, holistic HLS optimizers) fold WLO into a larger
  non-linear program instead of treating it as a separate pass.
- **Mixed number formats.** Not just FWL search — learn *per-layer* whether
  to use fixed-point, posit, bfloat, or custom float (see TrueFloat and
  the 2026 Single-Path Precision paper).
- **Learned cost surrogates.** GNNs trained on prior synthesis runs to
  predict LUT / DSP / Fmax from a width vector in milliseconds, used
  inside gradient-based precision search.
- **Formal verification of fixed-point error bounds** (Gappa, FPTaylor,
  Daisy) feeding into WLO instead of relying on sim-only bounds.

---

## Sources

- [Enhanced Precision Analysis for Accuracy-Aware Bit-Width Optimization Using Affine Arithmetic (IEEE)](https://ieeexplore.ieee.org/document/6663240/)
- [Accuracy-Guaranteed Bit-Width Optimization (Dong/Constantinides, Imperial)](https://cas.ee.ic.ac.uk/people/gac1/pubs/DongUTCAD06.pdf)
- [Unifying Bit-width Optimisation for Fixed-point and Floating-point Designs (Imperial, FCCM)](http://comparch.doc.ic.ac.uk/publications/files/alt04fccm.pdf)
- [Tradeoff between Approximation Accuracy and Complexity for Range Analysis using Affine Arithmetic (Springer)](https://link.springer.com/article/10.1007/s11265-010-0452-2)
- [Fast Integer Word-length Optimization for Fixed-point Systems (Springer JSPS)](https://link.springer.com/article/10.1007/s11265-015-0990-8)
- [Wordlength Optimization of Fixed-Point Algorithms (Springer chapter)](https://link.springer.com/chapter/10.1007/978-3-030-94705-7_9)
- [Automated Fixed-Point Precision Optimization for FPGA Synthesis (2025)](https://www.researchgate.net/publication/392823955_Automated_Fixed-Point_Precision_Optimization_for_FPGA_Synthesis)
- [Single-Path Precision: Differentiable Bit-Width & Numeric-Format Learning for FPGA-Efficient Neural Networks (Springer, 2026)](https://link.springer.com/chapter/10.1007/978-3-032-10192-1_35)
- [Holistic Optimization Framework for FPGA Accelerators (Prometheus, arXiv 2501.09242)](https://arxiv.org/html/2501.09242v4)
- [Automated Python-to-RTL Transformation and Optimization (Tsinghua, ISEDA 2024)](https://numbda.cs.tsinghua.edu.cn/papers/iseda24.pdf)
- [FPGA HLS Today: Successes, Challenges, and Opportunities (ACM TRETS)](https://dl.acm.org/doi/full/10.1145/3530775)
- [EqMap: FPGA LUT Remapping using E-Graphs (ICCAD 2025)](https://www.csl.cornell.edu/~zhiruz/pdfs/eqmap-iccad2025.pdf)
- [Minimizing FPGA Resource Utilization (ZipCPU)](https://zipcpu.com/blog/2017/06/12/minimizing-luts.html)
- [Chisel Width Inference](https://www.chisel-lang.org/docs/explanations/width-inference)
- [PyRTL documentation](https://ucsbarchlab.github.io/PyRTL/)
- [MyHDL hardware-oriented types](http://docs.myhdl.org/en/stable/manual/hwtypes.html)
