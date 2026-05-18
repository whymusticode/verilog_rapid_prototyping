#ifndef KERNEL_H
#define KERNEL_H

#include <ap_int.h>
#include <ap_fixed.h>
#include <hls_math.h>

// Project configuration
#define MATRIX_SIZE 10
#define MAX_ITERATIONS 2000
#define CONVERGENCE_THRESHOLD 164  // 1e-8 * 2^14 ≈ 0.000164 in fixed-point

// Fixed-point configuration from project.yaml
#define TOTAL_BITS 46
#define FRAC_BITS 14
#define INT_BITS (TOTAL_BITS - FRAC_BITS)

// Fixed-point types
typedef ap_fixed<TOTAL_BITS, INT_BITS> fixed_t;
typedef ap_fixed<TOTAL_BITS*2, INT_BITS*2> fixed_mult_t;  // For intermediate products

// Complex number structure
struct complex_t {
    fixed_t re;
    fixed_t im;
    
    complex_t() : re(0), im(0) {}
    complex_t(fixed_t r, fixed_t i) : re(r), im(i) {}
};

// Complex arithmetic operations
inline complex_t complex_mult(const complex_t& a, const complex_t& b) {
    complex_t result;
    // (a.re + j*a.im) * (b.re + j*b.im) = (a.re*b.re - a.im*b.im) + j*(a.re*b.im + a.im*b.re)
    fixed_mult_t re_prod1 = (fixed_mult_t)a.re * (fixed_mult_t)b.re;
    fixed_mult_t re_prod2 = (fixed_mult_t)a.im * (fixed_mult_t)b.im;
    fixed_mult_t im_prod1 = (fixed_mult_t)a.re * (fixed_mult_t)b.im;
    fixed_mult_t im_prod2 = (fixed_mult_t)a.im * (fixed_mult_t)b.re;
    
    result.re = (fixed_t)(re_prod1 - re_prod2);
    result.im = (fixed_t)(im_prod1 + im_prod2);
    return result;
}

inline complex_t complex_conj(const complex_t& a) {
    return complex_t(a.re, -a.im);
}

inline complex_t complex_add(const complex_t& a, const complex_t& b) {
    return complex_t(a.re + b.re, a.im + b.im);
}

inline complex_t complex_sub(const complex_t& a, const complex_t& b) {
    return complex_t(a.re - b.re, a.im - b.im);
}

inline fixed_t complex_abs(const complex_t& a) {
    // |a| = sqrt(re^2 + im^2)
    fixed_mult_t re_sq = (fixed_mult_t)a.re * (fixed_mult_t)a.re;
    fixed_mult_t im_sq = (fixed_mult_t)a.im * (fixed_mult_t)a.im;
    fixed_t sum = (fixed_t)(re_sq + im_sq);
    return hls::sqrt((float)sum);  // Using float for sqrt, convert back
}

inline fixed_t complex_angle(const complex_t& a) {
    // angle = atan2(im, re)
    return hls::atan2((float)a.im, (float)a.re);
}

// Top-level kernel function
void kernel_top(
    const ap_int<TOTAL_BITS> matrix_real_in[MATRIX_SIZE * MATRIX_SIZE],
    const ap_int<TOTAL_BITS> matrix_imag_in[MATRIX_SIZE * MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvalues_real_out[MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvalues_imag_out[MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvectors_real_out[MATRIX_SIZE * MATRIX_SIZE],
    ap_int<TOTAL_BITS> eigenvectors_imag_out[MATRIX_SIZE * MATRIX_SIZE],
    ap_uint<12>& iter_count,
    ap_uint<32>& cycles
);

#endif // KERNEL_H
