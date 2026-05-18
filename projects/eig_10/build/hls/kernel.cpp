#include "kernel.h"
#include <hls_math.h>

// Convert ap_int to fixed_t
static inline fixed_t int_to_fixed(ap_int<TOTAL_BITS> val) {
    fixed_t result;
    result.range() = val.range(TOTAL_BITS-1, 0);
    return result;
}

// Convert fixed_t to ap_int
static inline ap_int<TOTAL_BITS> fixed_to_int(fixed_t val) {
    ap_int<TOTAL_BITS> result;
    result.range(TOTAL_BITS-1, 0) = val.range();
    return result;
}

// Matrix multiplication: C = A * B (both complex)
static void matrix_mult(
    complex_t A[MATRIX_SIZE][MATRIX_SIZE],
    complex_t B[MATRIX_SIZE][MATRIX_SIZE],
    complex_t C[MATRIX_SIZE][MATRIX_SIZE]
) {
    #pragma HLS INLINE off
    
    // Initialize output
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            #pragma HLS PIPELINE II=1
            C[i][j].re = 0;
            C[i][j].im = 0;
        }
    }
    
    // Multiply
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            for (int k = 0; k < MATRIX_SIZE; k++) {
                #pragma HLS PIPELINE II=1
                complex_t prod = complex_mult(A[i][k], B[k][j]);
                C[i][j] = complex_add(C[i][j], prod);
            }
        }
    }
}

// Apply rotation: A_new = U^H * A * U
static void apply_rotation(
    complex_t A[MATRIX_SIZE][MATRIX_SIZE],
    complex_t U[MATRIX_SIZE][MATRIX_SIZE],
    complex_t temp[MATRIX_SIZE][MATRIX_SIZE],
    complex_t A_out[MATRIX_SIZE][MATRIX_SIZE]
) {
    #pragma HLS INLINE off
    
    // Create U^H (conjugate transpose)
    complex_t UH[MATRIX_SIZE][MATRIX_SIZE];
    #pragma HLS ARRAY_PARTITION variable=UH dim=0 complete
    
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            #pragma HLS PIPELINE II=1
            UH[i][j] = complex_conj(U[j][i]);
        }
    }
    
    // temp = A * U
    matrix_mult(A, U, temp);
    
    // A_out = U^H * temp
    matrix_mult(UH, temp, A_out);
}

void kernel_top(
    const ap_int<TOTAL_BITS> matrix_real_in[MATRIX_SIZE * MATRIX_SIZE],
    const ap_int<TOTAL_BITS> matrix_imag_in[MATRIX_SIZE * MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvalues_real_out[MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvalues_imag_out[MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvectors_real_out[MATRIX_SIZE * MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvectors_imag_out[MATRIX_SIZE * MATRIX_SIZE],
    ap_uint<12>& iter_count,
    ap_uint<32>& cycles
) {
    // Interface pragmas
    #pragma HLS INTERFACE mode=m_axi port=matrix_real_in bundle=gmem0 depth=100
    #pragma HLS INTERFACE mode=m_axi port=matrix_imag_in bundle=gmem1 depth=100
    #pragma HLS INTERFACE mode=m_axi port=eigenvalues_real_out bundle=gmem2 depth=10
    #pragma HLS INTERFACE mode=m_axi port=eigenvalues_imag_out bundle=gmem3 depth=10
    #pragma HLS INTERFACE mode=m_axi port=eigenvectors_real_out bundle=gmem4 depth=100
    #pragma HLS INTERFACE mode=m_axi port=eigenvectors_imag_out bundle=gmem5 depth=100
    #pragma HLS INTERFACE mode=s_axilite port=iter_count
    #pragma HLS INTERFACE mode=s_axilite port=cycles
    #pragma HLS INTERFACE mode=s_axilite port=return
    
    // Local matrices
    complex_t A[MATRIX_SIZE][MATRIX_SIZE];
    complex_t V[MATRIX_SIZE][MATRIX_SIZE];
    complex_t U[MATRIX_SIZE][MATRIX_SIZE];
    complex_t temp[MATRIX_SIZE][MATRIX_SIZE];
    complex_t A_new[MATRIX_SIZE][MATRIX_SIZE];
    
    #pragma HLS ARRAY_PARTITION variable=A dim=0 complete
    #pragma HLS ARRAY_PARTITION variable=V dim=0 complete
    #pragma HLS ARRAY_PARTITION variable=U dim=0 complete
    
    ap_uint<32> cycle_count = 0;
    
    // Load input matrix A
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            #pragma HLS PIPELINE II=1
            int idx = i * MATRIX_SIZE + j;
            A[i][j].re = int_to_fixed(matrix_real_in[idx]);
            A[i][j].im = int_to_fixed(matrix_imag_in[idx]);
        }
    }
    cycle_count += MATRIX_SIZE * MATRIX_SIZE;
    
    // Initialize V as identity matrix
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            #pragma HLS PIPELINE II=1
            if (i == j) {
                V[i][j].re = 1.0;
                V[i][j].im = 0.0;
            } else {
                V[i][j].re = 0.0;
                V[i][j].im = 0.0;
            }
        }
    }
    cycle_count += MATRIX_SIZE * MATRIX_SIZE;
    
    // Jacobi iteration
    ap_uint<12> z;
    for (z = 0; z < MAX_ITERATIONS; z++) {
        #pragma HLS LOOP_TRIPCOUNT min=10 max=100 avg=50
        
        // Find maximum off-diagonal element
        fixed_t off_diag_max = 0;
        ap_uint<4> p = 0;
        ap_uint<4> q = 1;
        
        for (int i = 0; i < MATRIX_SIZE; i++) {
            for (int j = i + 1; j < MATRIX_SIZE; j++) {
                #pragma HLS PIPELINE II=1
                fixed_t abs_val = complex_abs(A[i][j]);
                if (abs_val > off_diag_max) {
                    off_diag_max = abs_val;
                    p = i;
                    q = j;
                }
            }
        }
        cycle_count += (MATRIX_SIZE * (MATRIX_SIZE + 1)) / 2;
        
        // Check convergence
        if (off_diag_max < CONVERGENCE_THRESHOLD) {
            break;
        }
        
        // Get pivot elements
        complex_t a_pp = A[p][p];
        complex_t a_qq = A[q][q];
        complex_t a_pq = A[p][q];
        
        // Calculate rotation parameters
        // theta = 0.5 * arctan(2*|a_pq| / (a_pp - a_qq))
        // Note: for Hermitian matrices, a_pp and a_qq should be real
        fixed_t abs_a_pq = complex_abs(a_pq);
        fixed_t diff = a_pp.re - a_qq.re;
        
        fixed_t theta;
        if (hls::abs((float)diff) < 1e-10) {
            theta = 0.785398163;  // pi/4 in fixed-point
        } else {
            float theta_f = 0.5f * hls::atan(2.0f * (float)abs_a_pq / (float)diff);
            theta = theta_f;
        }
        
        // phi = -angle(a_pq)
        fixed_t phi = -complex_angle(a_pq);
        
        // Compute sin/cos
        fixed_t cos_theta = hls::cos((float)theta);
        fixed_t sin_theta = hls::sin((float)theta);
        fixed_t cos_phi = hls::cos((float)phi);
        fixed_t sin_phi = hls::sin((float)phi);
        
        cycle_count += 20;  // Estimate for trig operations
        
        // Build rotation matrix U as identity
        for (int i = 0; i < MATRIX_SIZE; i++) {
            for (int j = 0; j < MATRIX_SIZE; j++) {
                #pragma HLS PIPELINE II=1
                if (i == j) {
                    U[i][j].re = 1.0;
                    U[i][j].im = 0.0;
                } else {
                    U[i][j].re = 0.0;
                    U[i][j].im = 0.0;
                }
            }
        }
        
        // Set rotation elements
        // U[p,p] = cos(theta)
        U[p][p].re = cos_theta;
        U[p][p].im = 0;
        
        // U[p,q] = sin(theta) * exp(-j*phi) = sin(theta) * (cos(phi) - j*sin(phi))
        U[p][q].re = sin_theta * cos_phi;
        U[p][q].im = -sin_theta * sin_phi;
        
        // U[q,p] = sin(theta) * exp(j*phi) = sin(theta) * (cos(phi) + j*sin(phi))
        U[q][p].re = sin_theta * cos_phi;
        U[q][p].im = sin_theta * sin_phi;
        
        // U[q,q] = cos(theta) (corrected from reference bug)
        U[q][q].re = cos_theta;
        U[q][q].im = 0;
        
        cycle_count += MATRIX_SIZE * MATRIX_SIZE;
        
        // Apply rotation: A = U^H * A * U
        apply_rotation(A, U, temp, A_new);
        
        // Copy A_new to A
        for (int i = 0; i < MATRIX_SIZE; i++) {
            for (int j = 0; j < MATRIX_SIZE; j++) {
                #pragma HLS PIPELINE II=1
                A[i][j] = A_new[i][j];
            }
        }
        
        // Explicitly zero out pivoted elements
        A[p][q].re = 0;
        A[p][q].im = 0;
        A[q][p].re = 0;
        A[q][p].im = 0;
        
        cycle_count += MATRIX_SIZE * MATRIX_SIZE * MATRIX_SIZE * 3;  // Matrix mult estimate
        
        // Update eigenvectors: V = V * U
        matrix_mult(V, U, temp);
        for (int i = 0; i < MATRIX_SIZE; i++) {
            for (int j = 0; j < MATRIX_SIZE; j++) {
                #pragma HLS PIPELINE II=1
                V[i][j] = temp[i][j];
            }
        }
        
        cycle_count += MATRIX_SIZE * MATRIX_SIZE * MATRIX_SIZE + MATRIX_SIZE * MATRIX_SIZE;
    }
    
    // Extract eigenvalues (diagonal of A)
    for (int i = 0; i < MATRIX_SIZE; i++) {
        #pragma HLS PIPELINE II=1
        eigenvalues_real_out[i] = fixed_to_int(A[i][i].re);
        eigenvalues_imag_out[i] = fixed_to_int(A[i][i].im);
    }
    cycle_count += MATRIX_SIZE;
    
    // Write eigenvectors
    for (int i = 0; i < MATRIX_SIZE; i++) {
        for (int j = 0; j < MATRIX_SIZE; j++) {
            #pragma HLS PIPELINE II=1
            int idx = i * MATRIX_SIZE + j;
            eigenvectors_real_out[idx] = fixed_to_int(V[i][j].re);
            eigenvectors_imag_out[idx] = fixed_to_int(V[i][j].im);
        }
    }
    cycle_count += MATRIX_SIZE * MATRIX_SIZE;
    
    iter_count = z;
    cycles = cycle_count;
}
