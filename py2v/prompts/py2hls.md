# Python → Vitis HLS C++ (first draft)

Convert the **Translation Target Function** in the attached Python into synthesizable
Vitis HLS C++ (`ap_fixed` / `ap_int` per `params.yaml`).

## Deliverables — emit exactly these files using markers:

```
=== FILE: hls/kernel.h ===
...
=== FILE: hls/kernel.cpp ===
...
=== FILE: hls/tb.cpp ===
```

No markdown fences. No commentary outside the file blocks.

## Requirements

- Top function name: `kernel_top` (declared in `kernel.h`, defined in `kernel.cpp`).
- Match the Python function's inputs/outputs (names, arity, shapes) using fixed-point types
  derived from `params.yaml`. For each named tensor, compute:
  - bits per component = `bits + signed`
  - `ap_fixed<bits_per_component, bits_per_component - fraction>` for each real/imag component
  - total wire width = `(bits + signed) * (1 + complex)` (do NOT store this in params.yaml)
  - Real-only tensors use one `ap_fixed`; complex tensors use two (real + imag).
- `tb.cpp` C-simulation testbench must:
  - Run **call index 0 only** (first captured vector).
  - Read inputs from flat text files under the IO directory provided in the context
    (use that exact path string as a C string literal — do not compute it at runtime).
    Each line is one scalar; complex tensors use interleaved `real imag` per element.
  - Invoke `kernel_top` with those inputs.
  - Write each output tensor to the sim output directory provided in the context
    (same exact path string, same basename as reference capture).
    Same flat format as inputs.
- Kernel: C++17, HLS-friendly (no `malloc`, no iostream in `kernel.cpp`).
- **No `double` or `float` anywhere in `kernel.cpp` or `kernel.h`.** All arithmetic
  must use `ap_fixed` / `ap_int` types. Using floating-point internally defeats HLS
  synthesis and makes the C-sim cycle count meaningless.
- Minimal pragmas on `kernel_top` and one inner loop.
- Add a `uint32_t &clock_cycles` output argument to `kernel_top`. Inside the kernel,
  count every loop iteration that executes and accumulate into `clock_cycles` before
  returning. This is a C-sim proxy for hardware cycle count (proportional to latency).
- In `tb.cpp`, after calling `kernel_top`, write `clock_cycles` to
  `<SIM_DIR>clock_cycles.txt` as a single integer line.

When all three files are complete, stop.
