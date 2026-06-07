module top #(
    parameter N = 10,
    parameter W = 46
)(
    input  wire clk,
    input  wire rst,
    input  wire start,
    input  wire [N*N*W-1:0] a_re_in,
    input  wire [N*N*W-1:0] a_im_in,
    output wire [N*N*W-1:0] a_re_out,
    output wire [N*N*W-1:0] a_im_out,
    output wire [N*N*W-1:0] v_re_out,
    output wire [N*N*W-1:0] v_im_out,
    output reg  [15:0] iter_count,
    output reg  busy,
    output reg  done,
    output reg  [31:0] cycles
);

    wire [N*W-1:0] eigenvalues_real_dut;
    wire [N*N*W-1:0] eigenvectors_real_dut;
    wire [N*N*W-1:0] eigenvectors_imag_dut;
    wire valid_out_dut;
    wire [11:0] iterations_dut;
    
    reg valid_in_reg;
    reg start_prev;
    reg counting;
    
    // Instantiate the eigenvalue decomposition module
    eigenvalue_decomposition #(
        .MATRIX_SIZE(N),
        .COMPLEX_WIDTH(W),
        .MAX_ITERATIONS(2000)
    ) dut (
        .clk(clk),
        .rst(rst),
        .valid_in(valid_in_reg),
        .matrix_real(a_re_in),
        .matrix_imag(a_im_in),
        .eigenvalues_real(eigenvalues_real_dut),
        .eigenvectors_real(eigenvectors_real_dut),
        .eigenvectors_imag(eigenvectors_imag_dut),
        .valid_out(valid_out_dut),
        .iterations(iterations_dut)
    );
    
    // Reconstruct output matrix A (diagonal eigenvalues)
    genvar i, j;
    generate
        for (i = 0; i < N; i = i + 1) begin : gen_a_out_rows
            for (j = 0; j < N; j = j + 1) begin : gen_a_out_cols
                if (i == j) begin
                    assign a_re_out[(i*N + j)*W +: W] = eigenvalues_real_dut[i*W +: W];
                    assign a_im_out[(i*N + j)*W +: W] = {W{1'b0}};
                end else begin
                    assign a_re_out[(i*N + j)*W +: W] = {W{1'b0}};
                    assign a_im_out[(i*N + j)*W +: W] = {W{1'b0}};
                end
            end
        end
    endgenerate
    
    // Pass through eigenvectors
    assign v_re_out = eigenvectors_real_dut;
    assign v_im_out = eigenvectors_imag_dut;
    
    // Handshake and cycle counting
    always @(posedge clk) begin
        if (rst) begin
            valid_in_reg <= 0;
            start_prev <= 0;
            busy <= 0;
            done <= 0;
            cycles <= 0;
            iter_count <= 0;
            counting <= 0;
        end else begin
            start_prev <= start;
            
            // Detect rising edge of start
            if (start && !start_prev && !busy) begin
                valid_in_reg <= 1;
                busy <= 1;
                done <= 0;
                cycles <= 0;
                counting <= 1;
            end else begin
                valid_in_reg <= 0;
            end
            
            // Count cycles while busy
            if (counting) begin
                cycles <= cycles + 1;
            end
            
            // Detect completion
            if (valid_out_dut && busy) begin
                done <= 1;
                busy <= 0;
                counting <= 0;
                iter_count <= iterations_dut;
            end else if (done) begin
                done <= 0;
            end
        end
    end

endmodule
