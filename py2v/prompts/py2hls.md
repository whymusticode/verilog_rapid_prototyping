# Python → Vitis HLS C++ (first draft)

Convert the **Translation Target Function** in the attached Python into synthesizable
Vitis HLS C++ (`ap_fixed` / `ap_int` per `params.yaml`).

## Deliverables — emit exactly these two files using markers:

```
=== FILE: hls/kernel.h ===
...
=== FILE: hls/kernel.cpp ===
```

No markdown fences. No commentary outside the file blocks. Do NOT emit tb.cpp.

## Naming convention (tb.cpp is generated automatically — follow this exactly)

Inputs and outputs are numbered by their order in `manifest.json` (inputs separately
from outputs, both 0-indexed). Use these names verbatim:

- Input types:     `in0_t`, `in1_t`, ...
- Output types:    `out0_t`, `out1_t`, ...
- Input variables: `in0`, `in1`, ... (arrays keep their shape)
- Output variables:`out0`, `out1`, ... (arrays keep their shape)
- Dimension macros:`DIM_IN0_0`, `DIM_IN0_1`, ... / `DIM_OUT0_0`, `DIM_OUT0_1`, ...
- Complex types are structs with `.re` and `.im` fields of the scalar type.
- Top function: `kernel_top`, declared in `kernel.h`, defined in `kernel.cpp`.

Example for a complex 2-D input tensor (index 0):
```cpp
typedef ap_fixed<23, 23> in0_scalar_t;
struct in0_t { in0_scalar_t re, im; };
#define DIM_IN0_0 10
#define DIM_IN0_1 10
```

## Requirements

- Match the Python function's inputs/outputs (names, arity, shapes) using fixed-point
  types derived from `params.yaml`. For each named tensor, compute:
  - bits per component = `bits + signed`
  - `ap_fixed<bits_per_component, bits_per_component - fraction>` for each component
  - Real-only tensors use one `ap_fixed`; complex tensors use a struct with `.re`/`.im`.
- Scalar outputs are passed by pointer (`out0_t *out0`).
- Array outputs are passed as arrays (`out1_t out1[DIM_OUT1_0][DIM_OUT1_1]`).
- Kernel: C++17, HLS-friendly (no `malloc`, no `iostream` in `kernel.cpp`).
- **No `double` or `float` anywhere in `kernel.cpp` or `kernel.h`** — use `ap_fixed`/`ap_int` for all arithmetic, including intermediate values and transcendental approximations.
- Minimal pragmas on `kernel_top` and inner loops.

When both files are complete, stop.
