# Iterate (speed phase)

You have a correctness-passing HLS design. Optimize cycles aggressively while
keeping functional correctness and timing healthy.

The target cycle budget may be aspirational. Treat it as a direction, not a
reason to thrash. Prioritize measurable improvement each round.

Working style:
- Form a short plan for the next highest-leverage architectural change.
- Execute it.
- Measure with `run_sim` and `run_pnr`.
- Keep what helps; revert or pivot when it hurts.

You have architectural freedom (pipeline, parallelism, algorithm family, data
layout). Document major strategy shifts briefly in HLS comments.

Success:
- ideal: `run_sim.pass` and `run_pnr.fmax_mhz >= run_pnr.clock_mhz` and cycles <= target.
- acceptable best effort: clear cycle reduction trend with stable correctness
  and timing, plus explicit statement of the limiting bottleneck.

Stay within hw resource limits unless temporary exploratory spikes are required
to evaluate a candidate architecture.
