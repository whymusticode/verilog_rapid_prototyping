# Reference bug review

- **Incorrect rotation matrix structure in Jacobi method** (`page 5, lines in jacobi_eigen function`): The Jacobi rotation matrix construction `U[q, q] = -np.cos(theta)` is incorrect for a complex Hermitian matrix. In the standard Jacobi method for Hermitian matrices, the rotation should be unitary with `U[q, q] = np.cos(theta)` (positive, not negative); verify against Jacobi eigenvalue algorithm references for complex Hermitian case.

- **Inconsistent convergence threshold scale** (`page 4-5, jacobi_eigen function`): Convergence check `if off_diag_max < 1e-8` uses absolute tolerance without considering matrix magnitude. For matrices constructed from random integers with `BW=14`, elements can be O(10^8) or larger (from 100-element vector products), making `1e-8` potentially too strict or inappropriate; consider relative tolerance based on matrix norm.

- **Phase angle calculation may cause rotation errors** (`page 5, jacobi_eigen function`): The line `phi = -np.angle(a_pq)` extracts phase, but the subsequent rotation formulas combining `theta` and `phi` don't match standard Jacobi for complex Hermitian matrices. Standard approach zeroes out off-diagonal by matching phases; verify this construction produces correct Hermitian similarity transform `U.conj().T @ A @ U`.

- **Max iteration count mismatch** (`page 4 vs page 5`): Function definition shows `max_iter=2000` (page 4) but throughput requirement of 1 µs at 100-200 MHz (100-200 cycles) cannot accommodate 2000 iterations; this ~100× mismatch needs resolution for feasible hardware implementation.

- **Complex data format ambiguity** (`page 3-4`): "46-bit signed integer (complex)" is specified but unclear if this means 46 bits total (23+23 for real/imag) or 46 bits each component (92 total); clarify for HDL implementation planning.
