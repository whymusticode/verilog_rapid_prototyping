module eigenvalue_decomposition #(
    parameter MATRIX_SIZE = 10,
    parameter COMPLEX_WIDTH = 46,
    parameter MAX_ITERATIONS = 2000
)(
    input  wire clk,
    input  wire rst,
    input  wire valid_in,
    input  wire signed [MATRIX_SIZE*MATRIX_SIZE*COMPLEX_WIDTH-1:0] matrix_real,
    input  wire signed [MATRIX_SIZE*MATRIX_SIZE*COMPLEX_WIDTH-1:0] matrix_imag,
    output reg  signed [MATRIX_SIZE*COMPLEX_WIDTH-1:0] eigenvalues_real,
    output reg  signed [MATRIX_SIZE*MATRIX_SIZE*COMPLEX_WIDTH-1:0] eigenvectors_real,
    output reg  signed [MATRIX_SIZE*MATRIX_SIZE*COMPLEX_WIDTH-1:0] eigenvectors_imag,
    output reg  valid_out,
    output reg  [11:0] iterations
);

    localparam N = MATRIX_SIZE;
    localparam W = COMPLEX_WIDTH;
    localparam FRAC_BITS = 14;
    
    // State machine
    localparam IDLE = 0;
    localparam FIND_MAX_INIT = 1;
    localparam FIND_MAX_SEARCH = 2;
    localparam CALC_ANGLES = 3;
    localparam APPLY_ROTATION = 4;
    localparam UPDATE_A_ROW = 5;
    localparam UPDATE_A_COL = 6;
    localparam UPDATE_V = 7;
    localparam DONE = 8;
    
    reg [3:0] state;
    reg [11:0] iter_count;
    
    // Working matrices (stored as 1D arrays)
    reg signed [W-1:0] A_re [0:N*N-1];
    reg signed [W-1:0] A_im [0:N*N-1];
    reg signed [W-1:0] V_re [0:N*N-1];
    reg signed [W-1:0] V_im [0:N*N-1];
    
    // Temp storage for row/column updates
    reg signed [W-1:0] temp_row_re [0:N-1];
    reg signed [W-1:0] temp_row_im [0:N-1];
    reg signed [W-1:0] temp_col_re [0:N-1];
    reg signed [W-1:0] temp_col_im [0:N-1];
    
    // Max off-diagonal tracking
    reg signed [W-1:0] max_mag_sq;
    reg [3:0] max_p, max_q;
    reg [3:0] search_i, search_j;
    
    // Current pivot indices
    reg [3:0] p, q;
    
    // Rotation parameters
    reg signed [W-1:0] a_pp_re, a_qq_re, a_pq_re, a_pq_im;
    reg signed [W-1:0] a_pq_mag;
    reg signed [W-1:0] theta;
    reg signed [W-1:0] cos_theta, sin_theta;
    reg signed [W-1:0] exp_phi_re, exp_phi_im;
    
    // Update counters
    reg [3:0] update_idx;
    
    // Convergence threshold: 1e-8 at Q14 ≈ 0 (use small value)
    localparam signed [W-1:0] THRESHOLD = 46'd164; // ~1e-5 in Q14
    
    // Fixed-point constants (Q14)
    localparam signed [W-1:0] ONE = 46'd16384;  // 1.0 in Q14
    localparam signed [W-1:0] HALF = 46'd8192;  // 0.5 in Q14
    localparam signed [W-1:0] PI_4 = 46'd12867; // pi/4 in Q14
    
    // Helper: multiply two Q14 numbers
    function signed [W-1:0] qmul;
        input signed [W-1:0] a, b;
        reg signed [2*W-1:0] prod;
        begin
            prod = a * b;
            qmul = prod[FRAC_BITS+W-1:FRAC_BITS];
        end
    endfunction
    
    // Helper: compute magnitude squared
    function signed [W-1:0] mag_sq;
        input signed [W-1:0] re, im;
        reg signed [2*W-1:0] re_sq, im_sq, sum;
        begin
            re_sq = re * re;
            im_sq = im * im;
            sum = re_sq + im_sq;
            mag_sq = sum[FRAC_BITS+W-1:FRAC_BITS];
        end
    endfunction
    
    // Helper: approximate sqrt (Newton-Raphson, 2 iterations)
    function signed [W-1:0] approx_sqrt;
        input signed [W-1:0] x;
        reg signed [W-1:0] guess, next;
        reg signed [2*W-1:0] temp;
        begin
            if (x <= 0) begin
                approx_sqrt = 0;
            end else if (x < (ONE >> 2)) begin
                approx_sqrt = x << 1;
            end else begin
                guess = x >> 1;
                // Newton: x_new = (x + n/x) / 2
                temp = (x << FRAC_BITS) / (guess + 1);
                next = (guess + temp[W-1:0]) >> 1;
                approx_sqrt = next;
            end
        end
    endfunction
    
    // Helper: absolute value
    function signed [W-1:0] abs_val;
        input signed [W-1:0] x;
        begin
            abs_val = (x < 0) ? -x : x;
        end
    endfunction
    
    integer i, j, k;
    
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            valid_out <= 0;
            iter_count <= 0;
            iterations <= 0;
            max_mag_sq <= 0;
            max_p <= 0;
            max_q <= 1;
            p <= 0;
            q <= 1;
            search_i <= 0;
            search_j <= 0;
            update_idx <= 0;
            
            for (i = 0; i < N*N; i = i + 1) begin
                A_re[i] <= 0;
                A_im[i] <= 0;
                V_re[i] <= 0;
                V_im[i] <= 0;
            end
            
        end else begin
            case (state)
                IDLE: begin
                    valid_out <= 0;
                    if (valid_in) begin
                        // Load input matrix A
                        for (i = 0; i < N*N; i = i + 1) begin
                            A_re[i] <= matrix_real[i*W +: W];
                            A_im[i] <= matrix_imag[i*W +: W];
                        end
                        
                        // Initialize V as identity matrix
                        for (i = 0; i < N; i = i + 1) begin
                            for (j = 0; j < N; j = j + 1) begin
                                if (i == j) begin
                                    V_re[i*N + j] <= ONE;
                                    V_im[i*N + j] <= 0;
                                end else begin
                                    V_re[i*N + j] <= 0;
                                    V_im[i*N + j] <= 0;
                                end
                            end
                        end
                        
                        iter_count <= 0;
                        state <= FIND_MAX_INIT;
                    end
                end
                
                FIND_MAX_INIT: begin
                    search_i <= 0;
                    search_j <= 1;
                    max_mag_sq <= 0;
                    max_p <= 0;
                    max_q <= 1;
                    state <= FIND_MAX_SEARCH;
                end
                
                FIND_MAX_SEARCH: begin
                    // Sequential search for maximum off-diagonal element
                    if (search_i < N) begin
                        if (search_j < N) begin
                            if (search_j > search_i) begin
                                // Compare magnitude squared
                                if (mag_sq(A_re[search_i*N + search_j], A_im[search_i*N + search_j]) > max_mag_sq) begin
                                    max_mag_sq <= mag_sq(A_re[search_i*N + search_j], A_im[search_i*N + search_j]);
                                    max_p <= search_i;
                                    max_q <= search_j;
                                end
                            end
                            search_j <= search_j + 1;
                        end else begin
                            search_i <= search_i + 1;
                            search_j <= search_i + 2;
                        end
                    end else begin
                        // Search complete, check convergence
                        a_pq_mag <= approx_sqrt(max_mag_sq);
                        if (max_mag_sq < qmul(THRESHOLD, THRESHOLD) || iter_count >= MAX_ITERATIONS) begin
                            state <= DONE;
                        end else begin
                            p <= max_p;
                            q <= max_q;
                            state <= CALC_ANGLES;
                        end
                    end
                end
                
                CALC_ANGLES: begin
                    // Extract pivot elements
                    a_pp_re <= A_re[p*N + p];
                    a_qq_re <= A_re[q*N + q];
                    a_pq_re <= A_re[p*N + q];
                    a_pq_im <= A_im[p*N + q];
                    
                    // Compute theta (simplified: use pi/4 for now)
                    // In full implementation: theta = 0.5 * arctan(2*|a_pq| / |a_pp - a_qq|)
                    theta <= PI_4;
                    
                    // Compute cos and sin of theta
                    cos_theta <= 46'sd11585; // cos(pi/4) ≈ 0.707 in Q14
                    sin_theta <= 46'sd11585; // sin(pi/4) ≈ 0.707 in Q14
                    
                    // Compute exp(-j*phi) where phi = angle(a_pq)
                    // Simplified: normalize a_pq to get exp(-j*phi)
                    if (a_pq_mag > 0) begin
                        exp_phi_re <= qmul(A_re[p*N + q], (ONE << FRAC_BITS) / (a_pq_mag + 1));
                        exp_phi_im <= -qmul(A_im[p*N + q], (ONE << FRAC_BITS) / (a_pq_mag + 1));
                    end else begin
                        exp_phi_re <= ONE;
                        exp_phi_im <= 0;
                    end
                    
                    state <= APPLY_ROTATION;
                end
                
                APPLY_ROTATION: begin
                    // Zero out the pivot elements manually
                    A_re[p*N + q] <= 0;
                    A_im[p*N + q] <= 0;
                    A_re[q*N + p] <= 0;
                    A_im[q*N + p] <= 0;
                    
                    // Update diagonal elements (simplified Jacobi update)
                    // In full: would compute new a_pp and a_qq based on rotation
                    // For now: approximate update
                    A_re[p*N + p] <= a_pp_re - qmul(qmul(sin_theta, sin_theta), a_pq_mag);
                    A_re[q*N + q] <= a_qq_re + qmul(qmul(sin_theta, sin_theta), a_pq_mag);
                    
                    update_idx <= 0;
                    state <= UPDATE_A_ROW;
                end
                
                UPDATE_A_ROW: begin
                    // Update rows p and q of A (excluding diagonal and pivot)
                    if (update_idx < N) begin
                        if (update_idx != p && update_idx != q) begin
                            // Update A[p, update_idx] and A[q, update_idx]
                            // Simplified rotation application
                            temp_row_re[update_idx] <= qmul(A_re[p*N + update_idx], cos_theta) + 
                                                        qmul(A_re[q*N + update_idx], sin_theta);
                            temp_row_im[update_idx] <= qmul(A_im[p*N + update_idx], cos_theta) + 
                                                        qmul(A_im[q*N + update_idx], sin_theta);
                        end
                        update_idx <= update_idx + 1;
                    end else begin
                        // Apply temp values back
                        for (i = 0; i < N; i = i + 1) begin
                            if (i != p && i != q) begin
                                A_re[p*N + i] <= temp_row_re[i];
                                A_im[p*N + i] <= temp_row_im[i];
                            end
                        end
                        update_idx <= 0;
                        state <= UPDATE_A_COL;
                    end
                end
                
                UPDATE_A_COL: begin
                    // Update columns p and q of A (excluding diagonal and pivot)
                    if (update_idx < N) begin
                        if (update_idx != p && update_idx != q) begin
                            // Update A[update_idx, p] and A[update_idx, q]
                            temp_col_re[update_idx] <= qmul(A_re[update_idx*N + p], cos_theta) - 
                                                        qmul(A_re[update_idx*N + q], sin_theta);
                            temp_col_im[update_idx] <= qmul(A_im[update_idx*N + p], cos_theta) - 
                                                        qmul(A_im[update_idx*N + q], sin_theta);
                        end
                        update_idx <= update_idx + 1;
                    end else begin
                        // Apply temp values back
                        for (i = 0; i < N; i = i + 1) begin
                            if (i != p && i != q) begin
                                A_re[i*N + p] <= temp_col_re[i];
                                A_im[i*N + p] <= temp_col_im[i];
                            end
                        end
                        update_idx <= 0;
                        state <= UPDATE_V;
                    end
                end
                
                UPDATE_V: begin
                    // Update eigenvector matrix V = V * U
                    // Update columns p and q of V
                    if (update_idx < N) begin
                        temp_row_re[update_idx] <= qmul(V_re[update_idx*N + p], cos_theta) + 
                                                    qmul(V_re[update_idx*N + q], sin_theta);
                        temp_row_im[update_idx] <= qmul(V_im[update_idx*N + p], cos_theta) + 
                                                    qmul(V_im[update_idx*N + q], sin_theta);
                        
                        temp_col_re[update_idx] <= -qmul(V_re[update_idx*N + p], sin_theta) + 
                                                     qmul(V_re[update_idx*N + q], cos_theta);
                        temp_col_im[update_idx] <= -qmul(V_im[update_idx*N + p], sin_theta) + 
                                                     qmul(V_im[update_idx*N + q], cos_theta);
                        
                        update_idx <= update_idx + 1;
                    end else begin
                        // Apply updates
                        for (i = 0; i < N; i = i + 1) begin
                            V_re[i*N + p] <= temp_row_re[i];
                            V_im[i*N + p] <= temp_row_im[i];
                            V_re[i*N + q] <= temp_col_re[i];
                            V_im[i*N + q] <= temp_col_im[i];
                        end
                        
                        // Next iteration
                        iter_count <= iter_count + 1;
                        state <= FIND_MAX_INIT;
                    end
                end
                
                DONE: begin
                    // Extract diagonal (eigenvalues)
                    for (i = 0; i < N; i = i + 1) begin
                        eigenvalues_real[i*W +: W] <= A_re[i*N + i];
                    end
                    
                    // Output eigenvectors
                    for (i = 0; i < N*N; i = i + 1) begin
                        eigenvectors_real[i*W +: W] <= V_re[i];
                        eigenvectors_imag[i*W +: W] <= V_im[i];
                    end
                    
                    iterations <= iter_count;
                    valid_out <= 1;
                    state <= IDLE;
                end
                
                default: state <= IDLE;
            endcase
        end
    end

endmodule
