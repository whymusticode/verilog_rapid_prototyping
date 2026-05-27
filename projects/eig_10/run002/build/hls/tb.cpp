#include "kernel.h"
#include <iostream>
#include <fstream>
#include <cstdlib>
#include <cmath>

using namespace std;

// Helper to convert fixed-point to integer representation
long long fixed_to_int(fixed_t val) {
    // Scale by 2^28 (frac_bits) to get integer representation
    const long long scale = 1LL << 28;
    return (long long)(val.to_double() * scale);
}

// Helper to convert integer representation to fixed-point
fixed_t int_to_fixed(long long val) {
    const double scale = (double)(1LL << 28);
    return fixed_t(val / scale);
}

int main() {
    // Read input matrix from reference_inputs.txt
    ifstream infile("../reference_inputs.txt");
    if (!infile.is_open()) {
        cerr << "Error: Cannot open ../reference_inputs.txt" << endl;
        return 1;
    }
    
    complex_t A_in[N*N];
    
    // Read N*N complex values (row-major order)
    for (int i = 0; i < N*N; i++) {
        long long re_int, im_int;
        if (!(infile >> re_int >> im_int)) {
            cerr << "Error: Failed to read input at position " << i << endl;
            return 1;
        }
        A_in[i].re = int_to_fixed(re_int);
        A_in[i].im = int_to_fixed(im_int);
    }
    infile.close();
    
    cout << "Input matrix loaded successfully." << endl;
    
    // Output arrays
    complex_t A_out[N*N];
    complex_t V_out[N*N];
    int iter_count = 0;
    int cycles = 0;
    
    // Call the HLS kernel
    cout << "Running kernel_top..." << endl;
    kernel_top(A_in, A_out, V_out, iter_count, cycles);
    cout << "Kernel execution complete." << endl;
    
    // Create sim directory if it doesn't exist
    system("mkdir -p ../sim");
    
    // Write diagonal elements (eigenvalues) to sim_diag_out.txt
    ofstream diag_out("../sim/sim_diag_out.txt");
    if (!diag_out.is_open()) {
        cerr << "Error: Cannot create ../sim/sim_diag_out.txt" << endl;
        return 1;
    }
    
    cout << "Writing diagonal elements (eigenvalues):" << endl;
    for (int i = 0; i < N; i++) {
        long long re_int = fixed_to_int(A_out[i * N + i].re);
        long long im_int = fixed_to_int(A_out[i * N + i].im);
        diag_out << re_int << " " << im_int << endl;
        cout << "  [" << i << "] re=" << re_int << " im=" << im_int 
             << " (float: " << A_out[i * N + i].re.to_double() << " + " 
             << A_out[i * N + i].im.to_double() << "j)" << endl;
    }
    diag_out.close();
    
    // Write metadata to sim_meta.txt
    ofstream meta_out("../sim/sim_meta.txt");
    if (!meta_out.is_open()) {
        cerr << "Error: Cannot create ../sim/sim_meta.txt" << endl;
        return 1;
    }
    
    meta_out << "iter_count " << iter_count << endl;
    meta_out << "cycles " << cycles << endl;
    meta_out.close();
    
    cout << endl;
    cout << "Metadata:" << endl;
    cout << "  Iterations: " << iter_count << endl;
    cout << "  Cycles: " << cycles << endl;
    
    // Optional: Write full eigenvector matrix for debugging
    ofstream vec_out("../sim/sim_eigenvectors.txt");
    if (vec_out.is_open()) {
        for (int i = 0; i < N*N; i++) {
            long long re_int = fixed_to_int(V_out[i].re);
            long long im_int = fixed_to_int(V_out[i].im);
            vec_out << re_int << " " << im_int << endl;
        }
        vec_out.close();
        cout << "Eigenvectors written to ../sim/sim_eigenvectors.txt" << endl;
    }
    
    // Optional: Write full output matrix for debugging
    ofstream mat_out("../sim/sim_matrix_out.txt");
    if (mat_out.is_open()) {
        for (int i = 0; i < N*N; i++) {
            long long re_int = fixed_to_int(A_out[i].re);
            long long im_int = fixed_to_int(A_out[i].im);
            mat_out << re_int << " " << im_int << endl;
        }
        mat_out.close();
        cout << "Output matrix written to ../sim/sim_matrix_out.txt" << endl;
    }
    
    cout << endl;
    cout << "Testbench completed successfully." << endl;
    
    return 0;
}
