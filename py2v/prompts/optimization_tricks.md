# LLMs may edit this file, this is where we keep track of what we include in optimization_tricks_prompts, don't include this file in prompts as this is where we keep track of what works and what doesn't. 

## 1. Combinational Logic Restructuring

1. ★ **Operator strength reduction**: replace `*` by constant with shift-add decomposition (e.g., `x*9` → `(x<<3)+x`).
2. ★ **Division/modulo by power-of-2** → shift/mask; non-power-of-2 constant division → reciprocal multiply.
3. **Factor common subexpressions** into shared wires instead of trusting synthesis to find them.
4. ★ **Boolean simplification across `if/else` chains** (consensus, absorption) that synthesis misses due to don't-care obscuring.
5. **Priority `if/else if` → parallel `case`** when conditions are mutually exclusive (▼, cuts mux depth).
6. ★ **`casez`/wildcard encoding** to collapse many case items into one (▼).
7. **Deliberate don't-cares** (`'x` default assignments) to give synthesis freedom to minimize.
8. ★ **Mux tree balancing**: restructure nested ternaries into balanced trees to cut critical path.
9. **One-hot mux → AND-OR reduction** (`|(sel & data)` structures).
10. ★ **Reduction operators** (`&x`, `|x`, `^x`) instead of explicit comparisons to all-ones/all-zero (▼).
11. **Comparison sharing**: compute `a-b` once, derive `<`, `==`, `>` from sign/zero flags.
12. ★ **Range checks** `(x >= LO && x <= HI)` → single subtract-compare, or mask trick when range is aligned.
13. **Equality against constants** → bit-pattern matching instead of full comparator.
14. ★ **Carry-save arithmetic**: keep multi-operand adds in carry-save form, resolve with one final adder.
15. **Constant folding & propagation** through module boundaries (pre-evaluate parameter math).
16. ★ **Dual-use subtractor**: `a-b` and `b-a` share hardware via conditional negation.
17. **Absorbing adjacent muxes**: merge cascaded 2:1 muxes with related selects into one wider mux.
18. ★ **Sign-extension tricks**: `{{N{x[MSB]}}, x}` replicate instead of arithmetic ops; watch signed/unsigned semantics.
19. **XOR-based conditional invert** (`x ^ {W{invert}}`) instead of mux between `x` and `~x` (▼).
20. **Increment/decrement fusion**: `sel ? a+1 : a-1` → `a + (sel ? 1 : -1)` → single adder with carry-in trick.

## 2. Arithmetic-Specific

21. ★ **Booth recoding awareness**: structure constant multipliers to minimize partial products.
22. **Shared multiplier**: time-multiplex one multiplier across operations instead of instantiating several.
23. ★ **Squaring specialization**: `x*x` has symmetric partial products—half the hardware of general multiply.
24. **Truncated/rounded arithmetic**: don't compute low bits you'll discard; use truncated multipliers.
25. ★ **Modulo counters via wrap detection**: `cnt == MAX-1` compare instead of `% MAX` (▼ in hardware cost).
26. **Gray code counters** for clock-domain-crossing pointers.
27. ★ **Carry-in exploitation**: `a + b + 1` as single adder with cin, not two adders; `a - b` = `a + ~b + 1`.
28. **Saturation logic sharing**: detect overflow once, mux to saturated value; avoid duplicated clamp trees.
29. ★ **Leading-zero count via priority encoder patterns** rather than loops that unroll badly.
30. **Constant comparison chains → thermometer/priority encode** structures.
31. ★ **Redundant number systems** (carry-save, signed-digit) inside iterative datapaths (CORDIC, dividers).
32. **Bit-serial vs parallel tradeoff**: serialize rarely-used wide arithmetic to save area.

## 3. Sequential / Register Optimizations

33. ★ **Retiming hints**: manually move registers across combinational logic to balance stage delays.
34. **Register duplication for fanout**: replicate high-fanout control regs (synthesis sometimes needs the hint).
35. ★ **Enable extraction**: convert `if (en) q <= d;` patterns consistently so clock-gating can be inferred.
36. **Remove redundant resets**: only reset control state, not datapath regs (▼, saves reset network area).
37. ★ **Synchronous vs async reset consistency**—mixed styles block optimizations and cause tool warnings.
38. **Shift register inference**: code delay lines as `q <= {q[W-2:0], d}` so SRL/shift primitives infer (▼).
39. ★ **One-hot vs binary vs Gray FSM encoding**—choose per FSM size/speed; don't default to binary.
40. **FSM state minimization**: merge equivalent states; LLMs often generate redundant states across passes.
41. ★ **Output registration of FSMs** (registered Moore outputs) to break critical paths at module edges.
42. **Datapath/control separation**: pull datapath ops out of FSM case arms into shared always blocks (▼).
43. ★ **Pipeline balancing**: split long combinational cones; insert registers at logical midpoints, not arbitrarily.
44. **C-slow / interleaving** for throughput when latency is free.
45. ★ **Register merging**: combine flags updated under identical conditions into one vector register (▼).
46. **Toggle/pulse generation idioms**: `pulse <= a & ~a_d;` edge-detect patterns instead of FSMs (▼).
47. ★ **Don't re-register already-registered signals** crossing module boundaries (double-flopping non-CDC paths wastes latency).
48. **Load-enable vs recirculating mux awareness**: `q <= en ? d : q;` and enabled-flop are equivalent; write the enable form.

## 4. Memory & Storage

49. ★ **RAM inference patterns**: exact read/write coding templates so block RAM infers instead of flop arrays.
50. **Read-during-write behavior**: choose read-first/write-first explicitly to match target RAM primitive.
51. ★ **Output register on RAM reads** to enable built-in RAM output pipeline registers.
52. **Banking/partitioning**: split wide/deep memories to match physical primitive geometries.
53. ★ **ROM via `case`/initial + readmemh**: constant tables as ROM inference, not giant assign chains (▼).
54. **FIFO depth right-sizing** and using distributed RAM for shallow FIFOs.
55. ★ **Byte-enable structuring**: partial-write logic that maps to native byte enables, not read-modify-write.
56. **Register file port reduction**: reschedule accesses to reduce port count (ports are expensive).
57. ★ **Replace CAM-like search loops** with hashing or valid-bit + small comparator structures.

## 5. Structural / Hierarchy

58. ★ **Flatten trivial wrapper modules** (▼)—or keep hierarchy where synthesis boundaries help; be deliberate.
59. **Resource sharing across mutually exclusive branches**: one adder muxed, not adder-per-branch.
60. ★ **Common-case fast path / rare-case slow path** split (avoid penalizing every cycle for rare events).
61. **Parameterize repeated blocks with `generate`** loops instead of copy-paste instances (▼▼).
62. ★ **`generate` conditional elaboration** to strip unused features at compile time rather than gating at runtime.
63. **Function/task extraction** for repeated combinational expressions (▼)—synthesizable functions inline cleanly.
64. ★ **Port width minimization**: trim buses to actually-used widths; dead upper bits ripple cost everywhere.
65. **Wire vs register port discipline** and avoiding pass-through churn signals.
66. ★ **Tie-off and dangling-output cleanup**—explicitly sink/source unused ports so tools prune correctly.

## 6. Timing / Critical Path

67. ★ **Late-arriving signal restructuring**: move the late signal to the final mux/gate stage of the cone.
68. **Precompute under registers**: move logic before a register when the following stage is the bottleneck.
69. ★ **Speculative computation**: compute both outcomes in parallel, select late (trades area for speed).
70. **Replicate logic to reduce fanout** on critical nets.
71. ★ **Compare-against-zero preference**: restructure so comparisons are against 0 (free flags) not variables.
72. **Early termination flags**: pipeline a "will overflow / is zero" flag alongside data instead of recomputing.
73. ★ **Avoid combinational loops through module hierarchies**—often created accidentally in multi-pass edits.
74. **Register slicing of wide operations**: split a 128-bit add into pipelined halves with carry register.

## 7. Coding-Style Enablers (make later passes possible)

75. ★ **`always_comb`/`always_ff` (or strict Verilog-2001 discipline)** to expose latch/intent bugs early.
76. **Full case/default assignment first** (`out = '0;` then override) to kill latches and shrink case arms (▼).
77. ★ **One signal per always block vs grouped**—group signals updated by the same condition (▼); split unrelated ones.
78. **Named parameter/port connections** with `.*` or explicit names—refactor safety for later passes.
79. ★ **`localparam` for derived constants** (widths, counts) so a single edit re-sizes everything.
80. **`$clog2` for address/count widths** instead of hand-computed literals (▼, prevents width bugs).
81. ★ **Consistent signed arithmetic**: declare `signed` properly instead of manual sign-hacking (▼, and avoids the classic mixed signed/unsigned silent-unsigned bug).
82. **Packed structs/arrays (SV)** to bundle related signals; collapses port lists and assignments (▼▼).
83. ★ **Interfaces/modports (SV)** for repeated bus port lists (▼▼).
84. **Concatenation assignments** `{a, b, c} = bus;` instead of three slice assigns (▼).
85. ★ **Replication operator** `{N{pattern}}` for repeated constants/patterns (▼).
86. **`for` loops in always blocks** for regular per-bit/per-lane logic instead of unrolled copy-paste (▼▼).
87. ★ **Ternary chains → indexed part-select** `vec[i*W +: W]` for mux-by-index (▼).
88. **Implicit continuous assign in declaration** `wire x = a & b;` (▼).

## 8. Power

89. ★ **Operand isolation**: gate inputs of unused arithmetic units to stop toggling.
90. **Clock enable coverage**: maximize registers under enables for automatic clock gating.
91. ★ **Bus hold vs zeroing**: hold last value on idle buses instead of forcing to zero (kills toggle power).
92. **FSM idle-state encoding** near-zero Hamming distance to frequent states.
93. ★ **Memory access gating**: hold RAM enables low on idle cycles (RAM reads burn power).

## 9. Verification-Friendly Optimization Hygiene (multi-pass safety)

94. ★ **Preserve I/O behavior contracts**: never change reset values, latency, or handshake timing without flagging it.
95. **Assertion breadcrumbs**: add `assert property` for invariants before optimizing so later passes catch regressions.
96. ★ **X-propagation awareness**: optimizations that exploit don't-cares must not leak X into control logic.
97. **Latch audit after every pass**: check no `always_comb` path misses an assignment.
98. ★ **Width/truncation audit**: every pass, recheck implicit widths—refactors silently change expression widths.
99. **Equivalence-checkable steps**: keep each optimization pass small enough that LEC/simulation diff is tractable.
100. ★ **Delete dead code aggressively** (unused signals, unreachable states, stale debug logic)—multi-pass LLM editing accumulates cruft fast (▼▼).

---

### things to consider when designing pass ordering for an LLM optimizer

1. **Hygiene pass** (§9, §7): fix latches, widths, dead code, style enablers.
2. **Structural pass** (§5): generate loops, function extraction, hierarchy cleanup — shrinks LOC so later passes see more context.
3. **Logic/arithmetic pass** (§1, §2): strength reduction, sharing, mux restructuring.
4. **Sequential pass** (§3, §4): FSM encoding, pipelining, memory inference.
5. **Timing/power pass** (§6, §8): only after function is stable.
6. **Re-verify** (§9) after each pass.