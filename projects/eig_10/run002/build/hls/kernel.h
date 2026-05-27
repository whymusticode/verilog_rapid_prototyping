#ifndef KERNEL_H
#define KERNEL_H

#include <ap_int.h>
#include <ap_fixed.h>
#include <hls_math.h>

// Fixed-point configuration from project.yaml
// Total bits: 46, Fractional bits: 28
typedef ap_fixed<46, 18, AP_RND, AP_SAT> fixed_t;

// Matrix dimension
const int N = 10;

// Algorithm parameters
const int MAX_ITER = 2000;
const fixed_t CONV_THRESH = 1e-8;

// Complex number structure
struct complex_t {
    fixed_t re;
    fixed_t im;
    
    complex_t() : re(0), im(0) {}
    complex_t(fixed_t r, fixed_t i) : re(r), im(i) {}
};

// Complex arithmetic helpers
inline complex_t complex_add(complex_t a, complex_t b) {
    return complex_t(a.re + b.re, a.im + b.im);
}

inline complex_t complex_sub(complex_t a, complex_t b) {
    return complex_t(a.re - b.re, a.im - b.im);
}

inline complex_t complex_mul(complex_t a, complex_t b) {
    fixed_t re = a.re * b.re - a.im * b.im;
    fixed_t im = a.re * b.im + a.im * b.re;
    return complex_t(re, im);
}

inline complex_t complex_conj(complex_t a) {
    return complex_t(a.re, -a.im);
}

inline fixed_t complex_abs(complex_t a) {
    fixed_t re2 = a.re * a.re;
    fixed_t im2 = a.im * a.im;
    return hls::sqrt(re2 + im2);
}

inline fixed_t complex_angle(complex_t a) {
    return hls::atan2(a.im, a.re);
}

// Top-level HLS kernel function
void kernel_top(
    complex_t A_in[N*N],
    complex_t A_out[N*N],
    complex_t V_out[N*N],
    int &iter_count,
    int &cycles
);

#endif // KERNEL_H
