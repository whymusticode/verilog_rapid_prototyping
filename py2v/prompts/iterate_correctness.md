# Iterate (correctness phase)

Your objective is to make `run_sim` pass against `reference_eigenvalues.txt`
at integer-LSB tolerance. Keep changes focused and practical.

Use a plan-driven loop:
- Keep one current hypothesis about the dominant error source.
- Gather only the report snippets needed to validate or reject that hypothesis.
- Apply minimal edits in `rtl/` and `tb/`.
- Re-run `run_sim` to measure impact.

Important constraints:
- Do not modify `reference.py` or overwrite reference expectations.
- You may refactor RTL and testbench structure as needed.
- If evidence suggests scaling mismatch (uniform clipping or pervasive
  edge-of-range behavior), you may request `run_python_ref` to regenerate
  fresh reference vectors consistent with project fixed-point settings.

Stop when:
- `run_sim.pass == true`, or
- progress plateaus and you have a clear best-effort explanation of the current
  bottleneck.

At end of turn, include one concise sentence: current status + next best move.
