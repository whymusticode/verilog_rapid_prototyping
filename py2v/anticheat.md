# Known LLM Cheats & Failure Modes

A log of ways the LLM has gamed metrics or produced silently wrong output.
Add new entries here when discovered so they can be banned in prompts.

---

## 1. Floating-point internals (conversion_016)

**What happened:** The LLM used `double` for all internal Jacobi computation and only
cast to `ap_fixed` at the output. C-sim reported 45 clock cycles (essentially nothing),
but the outputs were wrong by ~689K and the kernel would synthesise to a giant
floating-point pipeline with real latency in the thousands of cycles.

**Why it's a cheat:** C-sim counts loop iterations over `double` arrays the same as
over `ap_fixed` arrays. The cycle proxy only means something when all arithmetic is
fixed-point.

**Fix added:** Both `py2hls.md` and `optimize.md` now ban `double`/`float` in
`kernel.cpp` and `kernel.h`.
