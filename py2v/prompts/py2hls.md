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
  from `params.yaml` `fixed_point.total_bits` and `fixed_point.frac_bits`.
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
- Minimal pragmas on `kernel_top` and one inner loop.

When all three files are complete, stop.
