# RTL Implementation Notes

## Overview
This is a first-draft RTL implementation of the Jacobi eigenvalue decomposition algorithm for 10x10 complex Hermitian matrices using 46-bit fixed-point arithmetic (Q14 format: 14 fractional bits).

## Architecture

### Module: eigenvalue_decomposition.v
The main DUT implementing the Jacobi iterative algorithm with the following states:
1. **IDLE**: Wait for valid_in, load input matrix
2. **FIND_MAX_INIT**: Initialize search parameters
3. **FIND_MAX_SEARCH**: Sequential search for maximum off-diagonal element
4. **CALC_ANGLES**: Compute rotation angles (theta, phi)
5. **APPLY_ROTATION**: Zero pivot elements and update diagonals
6. **UPDATE_A_ROW**: Update rows p and q of matrix A
7. **UPDATE_A_COL**: Update columns p and q of matrix A
8. **UPDATE_V**: Update eigenvector matrix V
9. **DONE**: Extract eigenvalues and signal completion

### Key Features
- **Fixed-point arithmetic**: Q14 format (14 fractional bits out of 46 total)
- **Convergence threshold**: ~1e-5 (simplified from 1e-8 due to Q14 precision)
- **Maximum iterations**: 2000 (configurable parameter)
- **Storage**: Uses reg arrays for matrices A (working) and V (eigenvectors)
- **Simplified rotation**: Uses fixed pi/4 angle for quick convergence testing
- **Sequential processing**: Operates on one element/row/column at a time

### Known Simplifications
1. **Rotation angles**: Currently uses fixed theta=pi/4 instead of computing optimal angle
2. **Trigonometric functions**: Uses precomputed cos/sin values instead of CORDIC
3. **Complex phase**: Simplified exp(j*phi) computation
4. **Matrix updates**: Simplified Givens rotation application
5. **Division/sqrt**: Uses approximations instead of full implementations

These simplifications allow the design to synthesize and run, but may require more iterations to converge or produce less accurate results than the full algorithm.

## Module: top.v
Standard handshake wrapper that:
- Instantiates eigenvalue_decomposition
- Converts start signal to valid_in pulse
- Tracks busy/done status
- Counts cycles from start to completion
- Reformats diagonal eigenvalues into full matrix output format

## Testbench: tb/tb_top.v
- Reads input matrix from reference_inputs.txt
- Drives start signal and waits for done
- Extracts diagonal eigenvalues and writes to sim/sim_diag_out.txt
- Writes metadata (iter_count, cycles) to sim/sim_meta.txt
- Includes timeout watchdog (1ms simulation time)

## Fixed-Point Format
- Total bits: 46
- Fractional bits: 14
- Integer bits: 32
- Range: approximately ±2^31 with precision of 2^-14 (~0.000061)
- ONE = 16384 (1.0 in Q14)

## Resource Considerations
- Memory: 10×10 complex matrices = 200 registers × 46 bits = 9,200 flip-flops
- Two full matrices (A and V) = 18,400 flip-flops for storage
- Additional temp storage for row/column updates
- Multipliers: Uses qmul function (should map to DSP blocks)
- Expected to fit within ZU7EV budget (230K LUTs, 1728 DSPs)

## Next Steps for Optimization
1. Implement proper CORDIC for trig functions
2. Add angle calculation logic (arctan, atan2)
3. Optimize rotation angle computation
4. Pipeline the matrix updates
5. Add convergence checking improvements
6. Increase fractional bits if precision is insufficient
