## 23-bit complex fixed-point contract

- External matrix and vector format is signed 23-bit integer per lane: `I[22:0]` and `Q[22:0]`.
- Complex sample packing is little-endian by 3-byte lane: `[I2 I1 I0 Q2 Q1 Q0]`.
- Numeric range per lane is `[-2^22, 2^22-1]`.
- Rounding is nearest-even at Python/host boundaries.
- Saturation at boundaries is hard clamp to signed 23-bit range.
- Internal multiply keeps full precision (`23x23 -> 46` bits signed).
- Complex multiply uses 3-mult identity:
  - `k1 = ar*br`
  - `k2 = ai*bi`
  - `k3 = (ar+ai)*(br+bi)`
  - `re = k1-k2`
  - `im = k3-k1-k2`
- Dot-product accumulator uses 8 guard bits over the complex product width.
- Jacobi rotation coefficients are represented in signed Q1.22.
- Matrix state (`A`) and eigenvector state (`V`) are rounded+saturated back to 23-bit lanes only at write-back boundaries.

## deterministic policy

- Host and RTL both use cyclic pivot order: `(0,1) (0,2) ... (8,9)` for one sweep.
- One sweep has exactly 45 pivots for `N=10`.
- Output packet order is deterministic:
  1. Header/status
  2. `diag(A)` eigenvalue estimate (10 complex)
  3. `V` matrix (100 complex, row-major)

## overflow observability

- Core exports counters:
  - `overflow_mul`
  - `overflow_acc`
  - `overflow_wb`
- Counters are included in UART status packet so host checks numerical stress.
