#include "kernel.h"
#include <hls_math.h>

// Helper function to find max off-diagonal element
void find_max_offdiag(complex_t A[N*N], fixed_t &max_val, int &p, int &q) {
    max_val = 0;
    p = 0;
    q = 1;
    
    FIND_MAX_I: for (int i = 0; i < N; i++) {
        FIND_MAX_J: for (int j = i + 1; j < N; j++) {
            #pragma HLS PIPELINE II=1
            fixed_t abs_val = complex_abs(A[i * N + j]);
            if (abs_val > max_val) {
                max_val = abs_val;
                p = i;
                q = j;
            }
        }
    }
}

// Apply Jacobi rotation to matrix A
void apply_rotation(complex_t A[N*N], complex_t V[N*N], int p, int q, int iter) {
    // Extract diagonal and off-diagonal elements
    fixed_t a_pp = A[p * N + p].re;  // Diagonal elements are real for Hermitian
    fixed_t a_qq = A[q * N + q].re;
    complex_t a_pq = A[p * N + q];
    
    // Calculate rotation angle theta
    fixed_t abs_apq = complex_abs(a_pq);
    fixed_t theta;
    
    // Avoid division by zero
    if (hls::abs(a_pp - a_qq) < 1e-10) {
        theta = 0.785398163;  // pi/4
    } else {
        theta = 0.5 * hls::atan(2.0 * abs_apq / (a_pp - a_qq));
    }
    
    // Calculate phase angle
    fixed_t phi = -complex_angle(a_pq);
    
    // Precompute sin/cos
    fixed_t c = hls::cos(theta);
    fixed_t s = hls::sin(theta);
    
    // Create rotation elements with phase
    complex_t u_pp(c, 0);
    complex_t u_pq(s * hls::cos(-phi), s * hls::sin(-phi));
    complex_t u_qp(s * hls::cos(phi), s * hls::sin(phi));
    complex_t u_qq(c, 0);  // Corrected: positive cos(theta) for unitary matrix
    
    // Temporary storage for row p and q
    complex_t temp_Ap[N];
    complex_t temp_Aq[N];
    complex_t temp_Vp[N];
    complex_t temp_Vq[N];
    
    // Store original rows
    STORE_ROWS: for (int j = 0; j < N; j++) {
        #pragma HLS UNROLL factor=2
        temp_Ap[j] = A[p * N + j];
        temp_Aq[j] = A[q * N + j];
        temp_Vp[j] = V[p * N + j];
        temp_Vq[j] = V[q * N + j];
    }
    
    // Update A: Apply U^H from left (rows p and q)
    UPDATE_A_ROWS: for (int j = 0; j < N; j++) {
        #pragma HLS PIPELINE II=1
        complex_t ap_j = temp_Ap[j];
        complex_t aq_j = temp_Aq[j];
        
        // Row p: U^H[p,:] * A = conj(u_pp) * A[p,:] + conj(u_qp) * A[q,:]
        complex_t new_ap = complex_add(
            complex_mul(complex_conj(u_pp), ap_j),
            complex_mul(complex_conj(u_qp), aq_j)
        );
        
        // Row q: U^H[q,:] * A = conj(u_pq) * A[p,:] + conj(u_qq) * A[q,:]
        complex_t new_aq = complex_add(
            complex_mul(complex_conj(u_pq), ap_j),
            complex_mul(complex_conj(u_qq), aq_j)
        );
        
        A[p * N + j] = new_ap;
        A[q * N + j] = new_aq;
    }
    
    // Update A: Apply U from right (columns p and q)
    UPDATE_A_COLS: for (int i = 0; i < N; i++) {
        #pragma HLS PIPELINE II=1
        complex_t a_ip = A[i * N + p];
        complex_t a_iq = A[i * N + q];
        
        // Col p: A * U[:,p] = A[:,p] * u_pp + A[:,q] * u_qp
        complex_t new_a_ip = complex_add(
            complex_mul(a_ip, u_pp),
            complex_mul(a_iq, u_qp)
        );
        
        // Col q: A * U[:,q] = A[:,p] * u_pq + A[:,q] * u_qq
        complex_t new_a_iq = complex_add(
            complex_mul(a_ip, u_pq),
            complex_mul(a_iq, u_qq)
        );
        
        A[i * N + p] = new_a_ip;
        A[i * N + q] = new_a_iq;
    }
    
    // Explicitly zero out off-diagonal elements
    A[p * N + q] = complex_t(0, 0);
    A[q * N + p] = complex_t(0, 0);
    
    // Update eigenvector matrix V = V * U
    UPDATE_V: for (int i = 0; i < N; i++) {
        #pragma HLS PIPELINE II=1
        complex_t v_ip = temp_Vp[i];
        complex_t v_iq = temp_Vq[i];
        
        // V[:,p] = V[:,p] * u_pp + V[:,q] * u_qp
        complex_t new_v_ip = complex_add(
            complex_mul(v_ip, u_pp),
            complex_mul(v_iq, u_qp)
        );
        
        // V[:,q] = V[:,p] * u_pq + V[:,q] * u_qq
        complex_t new_v_iq = complex_add(
            complex_mul(v_ip, u_pq),
            complex_mul(v_iq, u_qq)
        );
        
        V[i * N + p] = new_v_ip;
        V[i * N + q] = new_v_iq;
    }
}

// Top-level kernel function
void kernel_top(
    complex_t A_in[N*N],
    complex_t A_out[N*N],
    complex_t V_out[N*N],
    int &iter_count,
    int &cycles
) {
    #pragma HLS INTERFACE mode=m_axi port=A_in bundle=gmem0 depth=100
    #pragma HLS INTERFACE mode=m_axi port=A_out bundle=gmem1 depth=100
    #pragma HLS INTERFACE mode=m_axi port=V_out bundle=gmem2 depth=100
    #pragma HLS INTERFACE mode=s_axilite port=iter_count
    #pragma HLS INTERFACE mode=s_axilite port=cycles
    #pragma HLS INTERFACE mode=s_axilite port=return
    
    // Local storage for working matrices
    complex_t A[N*N];
    complex_t V[N*N];
    
    // Initialize A from input
    INIT_A: for (int i = 0; i < N*N; i++) {
        #pragma HLS PIPELINE II=1
        A[i] = A_in[i];
    }
    
    // Initialize V as identity matrix
    INIT_V: for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            #pragma HLS PIPELINE II=1
            if (i == j) {
                V[i * N + j] = complex_t(1.0, 0);
            } else {
                V[i * N + j] = complex_t(0, 0);
            }
        }
    }
    
    int cycle_count = 0;
    int iterations = 0;
    
    // Main Jacobi iteration loop
    JACOBI_LOOP: for (int z = 0; z < MAX_ITER; z++) {
        // Find maximum off-diagonal element
        fixed_t off_diag_max;
        int p, q;
        find_max_offdiag(A, off_diag_max, p, q);
        
        cycle_count += N * (N - 1) / 2;  // Approximate cycle count for search
        
        // Check convergence
        if (off_diag_max < CONV_THRESH) {
            iterations = z;
            break;
        }
        
        // Apply Jacobi rotation
        apply_rotation(A, V, p, q, z);
        
        cycle_count += 4 * N;  // Approximate cycle count for rotation
        iterations = z + 1;
    }
    
    // Copy results to output
    COPY_A: for (int i = 0; i < N*N; i++) {
        #pragma HLS PIPELINE II=1
        A_out[i] = A[i];
    }
    
    COPY_V: for (int i = 0; i < N*N; i++) {
        #pragma HLS PIPELINE II=1
        V_out[i] = V[i];
    }
    
    iter_count = iterations;
    cycles = cycle_count;
}
