#ifndef KERNEL_H
#define KERNEL_H

#include <ap_fixed.h>
#include <ap_int.h>
#include <hls_math.h>

// Fixed-point type: 46 total bits, 28 fractional bits
typedef ap_fixed<46, 18> fixed_t;

// Complex fixed-point pair
struct complex_t {
    fixed_t re;
    fixed_t im;
};

static const int N = 10;

// Outputs:
//   iters   : number of iterations performed (scalar int)
//   eigvals : diagonal of A after convergence (complex[N])
//   V       : eigenvector matrix (complex[N][N])
void kernel_top(
    const complex_t A_in[N][N],
    int             max_iter,
    int            &iters_out,
    complex_t       eigvals_out[N],
    complex_t       V_out[N][N]
);

#endif // KERNEL_H
