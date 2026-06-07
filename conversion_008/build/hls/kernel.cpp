#include "kernel.h"
#include <hls_math.h>

// ---------------------------------------------------------------------------
// Internal helpers (all in fixed-point / double for trig)
// ---------------------------------------------------------------------------

static void mat_mul(const complex_t A[N][N],
                    const complex_t B[N][N],
                    complex_t       C[N][N])
{
MAT_MUL_I:
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
            fixed_t re_acc = 0, im_acc = 0;
            for (int k = 0; k < N; k++) {
                re_acc += A[i][k].re * B[k][j].re - A[i][k].im * B[k][j].im;
                im_acc += A[i][k].re * B[k][j].im + A[i][k].im * B[k][j].re;
            }
            C[i][j].re = re_acc;
            C[i][j].im = im_acc;
        }
    }
}

// C = A_conj_T @ B  (i.e. C[i][j] = sum_k conj(A[k][i]) * B[k][j])
static void mat_conj_T_mul(const complex_t A[N][N],
                           const complex_t B[N][N],
                           complex_t       C[N][N])
{
MCTM_I:
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
            fixed_t re_acc = 0, im_acc = 0;
            for (int k = 0; k < N; k++) {
                // conj(A[k][i]) = (A[k][i].re, -A[k][i].im)
                re_acc += A[k][i].re * B[k][j].re + A[k][i].im * B[k][j].im;
                im_acc += A[k][i].re * B[k][j].im - A[k][i].im * B[k][j].re;
            }
            C[i][j].re = re_acc;
            C[i][j].im = im_acc;
        }
    }
}

// ---------------------------------------------------------------------------
// Top-level kernel
// ---------------------------------------------------------------------------
void kernel_top(
    const complex_t A_in[N][N],
    int             max_iter,
    int            &iters_out,
    complex_t       eigvals_out[N],
    complex_t       V_out[N][N]
)
{
#pragma HLS INTERFACE ap_none port=iters_out
#pragma HLS INTERFACE ap_none port=max_iter
#pragma HLS ARRAY_PARTITION variable=A_in   complete dim=0
#pragma HLS ARRAY_PARTITION variable=V_out  complete dim=0
#pragma HLS ARRAY_PARTITION variable=eigvals_out complete dim=1

    // Working copies
    complex_t A[N][N];
    complex_t V[N][N];

INIT_A:
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
            A[i][j] = A_in[i][j];
            V[i][j].re = (i == j) ? (fixed_t)1 : (fixed_t)0;
            V[i][j].im = 0;
        }
    }

    int z = 0;

JACOBI_ITER:
    for (int iter = 0; iter < 2000; iter++) {
#pragma HLS LOOP_TRIPCOUNT min=0 max=2000

        // ----- find max off-diagonal element -----
        fixed_t off_diag_max = 0;
        int p = 0, q = 1;

    FIND_MAX_I:
        for (int i = 0; i < N; i++) {
            for (int j = i + 1; j < N; j++) {
#pragma HLS PIPELINE II=1
                fixed_t re = A[i][j].re;
                fixed_t im = A[i][j].im;
                fixed_t abs2;
                // |a| ~ sqrt(re^2+im^2); compare squared to avoid sqrt
                abs2 = re * re + im * im;
                fixed_t cur_max_sq = off_diag_max * off_diag_max;
                if (abs2 > cur_max_sq) {
                    off_diag_max = hls::sqrt((double)abs2);
                    p = i;
                    q = j;
                }
            }
        }

        if (off_diag_max < (fixed_t)1e-8) {
            break;
        }

        z = iter;

        // ----- compute rotation parameters -----
        double a_pp_re = (double)A[p][p].re;
        double a_qq_re = (double)A[q][q].re;
        double a_pq_re = (double)A[p][q].re;
        double a_pq_im = (double)A[p][q].im;

        double abs_a_pq = hls::sqrt(a_pq_re * a_pq_re + a_pq_im * a_pq_im);
        double denom    = a_pp_re - a_qq_re;
        double theta, phi;

        // theta = 0.5 * arctan(2*|a_pq| / (a_pp - a_qq))
        if (denom == 0.0)
            theta = 3.14159265358979323846 / 4.0;
        else
            theta = 0.5 * hls::atan(2.0 * abs_a_pq / denom);

        // phi = -angle(a_pq)
        phi = -hls::atan2(a_pq_im, a_pq_re);

        double cos_t  = hls::cos(theta);
        double sin_t  = hls::sin(theta);
        double cos_p  = hls::cos(phi);
        double sin_p  = hls::sin(phi);

        // U[p,q] = sin(theta)*exp(-j*phi) = sin_t*(cos_p - j*sin_p)
        // U[q,p] = sin(theta)*exp(+j*phi) = sin_t*(cos_p + j*sin_p)
        // U[p,p] =  cos(theta),  U[q,q] = -cos(theta)

        fixed_t U_pp_re = (fixed_t)cos_t;
        fixed_t U_qq_re = (fixed_t)(-cos_t);
        fixed_t U_pq_re = (fixed_t)(sin_t * cos_p);
        fixed_t U_pq_im = (fixed_t)(-sin_t * sin_p);
        fixed_t U_qp_re = (fixed_t)(sin_t * cos_p);
        fixed_t U_qp_im = (fixed_t)(sin_t * sin_p);

        // Build dense U matrix
        complex_t U[N][N];
    BUILD_U:
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
                U[i][j].re = (i == j) ? (fixed_t)1 : (fixed_t)0;
                U[i][j].im = 0;
            }
        }
        U[p][p].re =  U_pp_re; U[p][p].im = 0;
        U[q][q].re =  U_qq_re; U[q][q].im = 0;
        U[p][q].re =  U_pq_re; U[p][q].im = U_pq_im;
        U[q][p].re =  U_qp_re; U[q][p].im = U_qp_im;

        // A = U^H @ A @ U
        complex_t tmp[N][N];
        mat_conj_T_mul(U, A, tmp);   // tmp  = U^H @ A
        complex_t A_new[N][N];
        mat_mul(tmp, U, A_new);       // A_new = tmp @ U

        // zero out p,q and q,p exactly
        A_new[p][q].re = 0; A_new[p][q].im = 0;
        A_new[q][p].re = 0; A_new[q][p].im = 0;

    COPY_A:
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
                A[i][j] = A_new[i][j];
            }
        }

        // V = V @ U
        complex_t V_new[N][N];
        mat_mul(V, U, V_new);
    COPY_V:
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
                V[i][j] = V_new[i][j];
            }
        }

        if (iter < max_iter - 1) {
            // continue
        } else {
            z = iter;
            break;
        }
    }

    iters_out = z;

OUT_EIG:
    for (int i = 0; i < N; i++) {
#pragma HLS PIPELINE II=1
        eigvals_out[i] = A[i][i];
    }

OUT_V:
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
#pragma HLS PIPELINE II=1
            V_out[i][j] = V[i][j];
        }
    }
}
