# Reference bug review

# Numerical and Algorithmic Issues Review

- **Incorrect rotation angle sign** (`jacobi_eigen:lines ~22-23`): The rotation matrix construction uses `-np.cos(theta)` for `U[q,q]`, which is incorrect for a standard Givens/Jacobi rotation. For Hermitian matrices, `U[q,q]` should be `np.cos(theta)` to maintain unitarity; verify against standard Jacobi formulation for complex Hermitian matrices.

- **Phase angle sign convention** (`jacobi_eigen:line ~22`): Using `phi = -np.angle(a_pq)` may not align with the standard Jacobi diagonalization convention for complex matrices. The sign of `phi` should be chosen to zero out the off-diagonal element correctly; verify this produces `U.conj().T @ A @ U` with zeroed `A[p,q]`.

- **Theta formula omits real part constraint** (`jacobi_eigen:line ~21`): The formula `theta = 0.5 * np.arctan((2 * np.abs(a_pq)) / (a_pp - a_qq))` uses absolute value but doesn't handle the case where `a_pp ≈ a_qq`, which could cause division by near-zero or require special handling (should default to π/4).

- **Missing convergence handling** (`jacobi_eigen:lines ~18-19`): The algorithm breaks when `off_diag_max < 1e-8` but doesn't report whether convergence was achieved; for hardware implementation planning, the caller should know if the result is valid or if max iterations were hit without convergence.

- **Hermitian property not enforced after update** (`jacobi_eigen:line ~30`): After the transformation `A = U.conj().T @ A @ U`, numerical errors can break Hermitian symmetry (`A[i,j] ≠ A[j,i].conj()`). Consider explicitly symmetrizing: `A = (A + A.conj().T) / 2` to maintain the Hermitian property throughout iterations.

- **Manual zero assignment may mask numerical accuracy** (`jacobi_eigen:line ~31`): Setting `A[p,q], A[q,p] = 0, 0` manually hides residual numerical error that could indicate transformation quality; consider letting these be computed values for accuracy assessment, or at least logging the pre-zeroing magnitude.

- **Iteration count not checked against max** (`jacobi_eigen:line ~33`): The function returns `z` (iteration count) but doesn't indicate whether this equals `max_iter` (non-convergence). Callers and hardware implementations need to distinguish between "converged at iteration z" vs "hit max iterations without convergence."

- **Complex number bitwidth mismatch** (`test code:line ~43-44`): Input generation uses `2**BW` with `BW=14` (14-bit integers), but the proposal specifies 46-bit signed integer format; clarify whether this generates 28-bit complex numbers (14+14) or if it's meant to test the 46-bit format mentioned in section 4.
