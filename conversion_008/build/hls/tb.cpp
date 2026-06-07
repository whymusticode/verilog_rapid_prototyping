#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include "kernel.h"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
static int read_scalar_int(const char *path, int *val)
{
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "Cannot open %s\n", path); return -1; }
    fscanf(f, "%d", val);
    fclose(f);
    return 0;
}

// Read N complex values (interleaved real imag per line) from file.
// Each element occupies one line: "re im"
static int read_complex_flat(const char *path, double *re, double *im, int n)
{
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "Cannot open %s\n", path); return -1; }
    for (int i = 0; i < n; i++) {
        if (fscanf(f, "%lf %lf", &re[i], &im[i]) != 2) {
            fprintf(stderr, "Parse error at element %d in %s\n", i, path);
            fclose(f);
            return -1;
        }
    }
    fclose(f);
    return 0;
}

static int write_scalar_int(const char *path, int val)
{
    FILE *f = fopen(path, "w");
    if (!f) { fprintf(stderr, "Cannot open %s for write\n", path); return -1; }
    fprintf(f, "%d\n", val);
    fclose(f);
    return 0;
}

static int write_complex_flat(const char *path, const double *re, const double *im, int n)
{
    FILE *f = fopen(path, "w");
    if (!f) { fprintf(stderr, "Cannot open %s for write\n", path); return -1; }
    for (int i = 0; i < n; i++) {
        fprintf(f, "%.17g %.17g\n", re[i], im[i]);
    }
    fclose(f);
    return 0;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
int main()
{
    // ---- paths ----
    const char *io_dir    = "../eig_10_io/";
    const char *sim_dir   = "sim/";

    // ---- storage ----
    double A_re[N][N], A_im[N][N];
    int    max_iter_val = 2000;

    // ---- read call index 0 ----
    // in_A.txt : N*N complex elements, interleaved re im, row-major
    {
        char path[256];
        snprintf(path, sizeof(path), "%sin_A.txt", io_dir);

        double flat_re[N * N], flat_im[N * N];
        if (read_complex_flat(path, flat_re, flat_im, N * N) != 0) return 1;
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++) {
                A_re[i][j] = flat_re[i * N + j];
                A_im[i][j] = flat_im[i * N + j];
            }
    }

    // in_max_iter.txt : one integer per call; read first line
    {
        char path[256];
        snprintf(path, sizeof(path), "%sin_max_iter.txt", io_dir);
        FILE *f = fopen(path, "r");
        if (!f) { fprintf(stderr, "Cannot open %s\n", path); return 1; }
        // file may contain int64 stored as text
        long long tmp = 2000;
        fscanf(f, "%lld", &tmp);
        fclose(f);
        max_iter_val = (int)tmp;
    }

    // ---- build kernel inputs ----
    complex_t A_kernel[N][N];
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++) {
            A_kernel[i][j].re = (fixed_t)A_re[i][j];
            A_kernel[i][j].im = (fixed_t)A_im[i][j];
        }

    // ---- kernel outputs ----
    int       iters_out = 0;
    complex_t eigvals_out[N];
    complex_t V_out[N][N];

    // ---- call kernel ----
    kernel_top(A_kernel, max_iter_val, iters_out, eigvals_out, V_out);

    // ---- write outputs ----
    // out_0.txt : scalar int (iteration count)
    {
        char path[256];
        snprintf(path, sizeof(path), "%sout_0.txt", sim_dir);
        if (write_scalar_int(path, iters_out) != 0) return 1;
    }

    // out_1.txt : eigvals complex[N]
    {
        char path[256];
        snprintf(path, sizeof(path), "%sout_1.txt", sim_dir);
        double re[N], im[N];
        for (int i = 0; i < N; i++) {
            re[i] = (double)eigvals_out[i].re;
            im[i] = (double)eigvals_out[i].im;
        }
        if (write_complex_flat(path, re, im, N) != 0) return 1;
    }

    // out_2.txt : V complex[N][N] row-major
    {
        char path[256];
        snprintf(path, sizeof(path), "%sout_2.txt", sim_dir);
        double re[N * N], im[N * N];
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++) {
                re[i * N + j] = (double)V_out[i][j].re;
                im[i * N + j] = (double)V_out[i][j].im;
            }
        if (write_complex_flat(path, re, im, N * N) != 0) return 1;
    }

    printf("kernel_top done. iters=%d\n", iters_out);
    return 0;
}
