#include "kernel.h"
#include <iostream>
#include <fstream>
#include <iomanip>
#include <cstdlib>
#include <string>

using namespace std;

int main() {
    // Input and output arrays
    ap_int<TOTAL_BITS> matrix_real_in[MATRIX_SIZE * MATRIX_SIZE];
    ap_int<TOTAL_BITS> matrix_imag_in[MATRIX_SIZE * MATRIX_SIZE];
    ap_int<TOTAL_BITS> eigenvalues_real_out[MATRIX_SIZE];
    ap_int<TOTAL_BITS> eigenvalues_imag_out[MATRIX_SIZE];
    ap_int<TOTAL_BITS> eigenvectors_real_out[MATRIX_SIZE * MATRIX_SIZE];
    ap_int<TOTAL_BITS> eigenvectors_imag_out[MATRIX_SIZE * MATRIX_SIZE];
    ap_uint<12> iter_count;
    ap_uint<32> cycles;
    
    // Read input matrix from reference_inputs.txt
    ifstream infile("../reference_inputs.txt");
    if (!infile.is_open()) {
        cerr << "Error: Could not open ../reference_inputs.txt" << endl;
        return 1;
    }
    
    cout << "Reading input matrix..." << endl;
    
    int line_num;
    long long re_val, im_val;
    char separator;
    string line;
    int elements_read = 0;
    
    while (getline(infile, line) && elements_read < MATRIX_SIZE * MATRIX_SIZE) {
        // Parse line format: "  N|re im"
        size_t pipe_pos = line.find('|');
        if (pipe_pos == string::npos) continue;
        
        string data_part = line.substr(pipe_pos + 1);
        istringstream iss(data_part);
        
        if (iss >> re_val >> im_val) {
            matrix_real_in[elements_read] = re_val;
            matrix_imag_in[elements_read] = im_val;
            elements_read++;
        }
    }
    infile.close();
    
    if (elements_read != MATRIX_SIZE * MATRIX_SIZE) {
        cerr << "Error: Expected " << MATRIX_SIZE * MATRIX_SIZE 
             << " elements, read " << elements_read << endl;
        return 1;
    }
    
    cout << "Successfully read " << elements_read << " complex elements" << endl;
    
    // Print first few input elements for verification
    cout << "\nFirst 10 input elements:" << endl;
    for (int i = 0; i < min(10, MATRIX_SIZE * MATRIX_SIZE); i++) {
        cout << "  [" << i << "] = " 
             << matrix_real_in[i].to_int64() << " + " 
             << matrix_imag_in[i].to_int64() << "j" << endl;
    }
    
    // Run the kernel
    cout << "\nRunning kernel_top..." << endl;
    kernel_top(
        matrix_real_in,
        matrix_imag_in,
        eigenvalues_real_out,
        eigenvalues_imag_out,
        eigenvectors_real_out,
        eigenvectors_imag_out,
        iter_count,
        cycles
    );
    
    cout << "Kernel completed!" << endl;
    cout << "Iterations: " << iter_count.to_uint() << endl;
    cout << "Cycles: " << cycles.to_uint() << endl;
    
    // Create sim directory if it doesn't exist
    system("mkdir -p ../sim");
    
    // Write diagonal outputs (eigenvalues) to sim/sim_diag_out.txt
    ofstream diagfile("../sim/sim_diag_out.txt");
    if (!diagfile.is_open()) {
        cerr << "Error: Could not create ../sim/sim_diag_out.txt" << endl;
        return 1;
    }
    
    cout << "\nEigenvalues (diagonal):" << endl;
    for (int i = 0; i < MATRIX_SIZE; i++) {
        long long re = eigenvalues_real_out[i].to_int64();
        long long im = eigenvalues_imag_out[i].to_int64();
        diagfile << re << " " << im << endl;
        cout << "  λ[" << i << "] = " << re << " + " << im << "j" << endl;
    }
    diagfile.close();
    cout << "Wrote eigenvalues to ../sim/sim_diag_out.txt" << endl;
    
    // Write metadata to sim/sim_meta.txt
    ofstream metafile("../sim/sim_meta.txt");
    if (!metafile.is_open()) {
        cerr << "Error: Could not create ../sim/sim_meta.txt" << endl;
        return 1;
    }
    
    metafile << "iter_count " << iter_count.to_uint() << endl;
    metafile << "cycles " << cycles.to_uint() << endl;
    metafile.close();
    cout << "Wrote metadata to ../sim/sim_meta.txt" << endl;
    
    // Optionally write eigenvectors for debugging
    ofstream vecfile("../sim/sim_eigenvectors.txt");
    if (vecfile.is_open()) {
        for (int i = 0; i < MATRIX_SIZE * MATRIX_SIZE; i++) {
            vecfile << eigenvectors_real_out[i].to_int64() << " "
                    << eigenvectors_imag_out[i].to_int64() << endl;
        }
        vecfile.close();
        cout << "Wrote eigenvectors to ../sim/sim_eigenvectors.txt" << endl;
    }
    
    cout << "\nTestbench completed successfully!" << endl;
    return 0;
}
