`timescale 1ns / 1ps

module tb_top;

    parameter N = 10;
    parameter W = 46;
    parameter CLK_PERIOD = 10; // 100 MHz clock
    parameter TIMEOUT = 1000000; // 1ms timeout
    
    reg clk;
    reg rst;
    reg start;
    reg [N*N*W-1:0] a_re_in;
    reg [N*N*W-1:0] a_im_in;
    wire [N*N*W-1:0] a_re_out;
    wire [N*N*W-1:0] a_im_out;
    wire [N*N*W-1:0] v_re_out;
    wire [N*N*W-1:0] v_im_out;
    wire [15:0] iter_count;
    wire busy;
    wire done;
    wire [31:0] cycles;
    
    // Instantiate DUT
    top #(
        .N(N),
        .W(W)
    ) dut (
        .clk(clk),
        .rst(rst),
        .start(start),
        .a_re_in(a_re_in),
        .a_im_in(a_im_in),
        .a_re_out(a_re_out),
        .a_im_out(a_im_out),
        .v_re_out(v_re_out),
        .v_im_out(v_im_out),
        .iter_count(iter_count),
        .busy(busy),
        .done(done),
        .cycles(cycles)
    );
    
    // Clock generation
    initial begin
        clk = 0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end
    
    // Test stimulus
    integer i, j;
    integer file_in, file_out, file_meta;
    integer scan_ret;
    reg signed [W-1:0] re_val, im_val;
    integer timeout_counter;
    
    initial begin
        // Initialize
        rst = 1;
        start = 0;
        a_re_in = {N*N*W{1'b0}};
        a_im_in = {N*N*W{1'b0}};
        timeout_counter = 0;
        
        // Reset sequence
        repeat(10) @(posedge clk);
        rst = 0;
        repeat(5) @(posedge clk);
        
        // Read input matrix from file
        file_in = $fopen("../reference_inputs.txt", "r");
        if (file_in == 0) begin
            $display("ERROR: Could not open reference_inputs.txt");
            $finish;
        end
        
        $display("Reading input matrix from reference_inputs.txt");
        for (i = 0; i < N*N; i = i + 1) begin
            scan_ret = $fscanf(file_in, "%d %d\n", re_val, im_val);
            if (scan_ret != 2) begin
                $display("ERROR: Failed to read element %0d", i);
                $finish;
            end
            a_re_in[i*W +: W] = re_val;
            a_im_in[i*W +: W] = im_val;
        end
        $fclose(file_in);
        
        $display("Input matrix loaded successfully");
        $display("Starting computation...");
        
        // Start computation
        @(posedge clk);
        start = 1;
        @(posedge clk);
        start = 0;
        
        // Wait for completion with timeout
        while (!done && timeout_counter < TIMEOUT) begin
            @(posedge clk);
            timeout_counter = timeout_counter + 1;
        end
        
        if (timeout_counter >= TIMEOUT) begin
            $display("ERROR: Timeout waiting for done signal");
            $finish;
        end
        
        $display("Computation completed in %0d cycles", cycles);
        $display("Iterations: %0d", iter_count);
        
        // Wait a few more cycles
        repeat(5) @(posedge clk);
        
        // Write output diagonal (eigenvalues) to file
        file_out = $fopen("sim/sim_diag_out.txt", "w");
        if (file_out == 0) begin
            $display("ERROR: Could not open sim/sim_diag_out.txt for writing");
            $finish;
        end
        
        $display("Writing eigenvalues to sim/sim_diag_out.txt");
        for (i = 0; i < N; i = i + 1) begin
            re_val = a_re_out[(i*N + i)*W +: W];
            im_val = a_im_out[(i*N + i)*W +: W];
            $fwrite(file_out, "%0d %0d\n", re_val, im_val);
        end
        $fclose(file_out);
        
        // Write metadata
        file_meta = $fopen("sim/sim_meta.txt", "w");
        if (file_meta == 0) begin
            $display("ERROR: Could not open sim/sim_meta.txt for writing");
            $finish;
        end
        
        $fwrite(file_meta, "iter_count %0d\n", iter_count);
        $fwrite(file_meta, "cycles %0d\n", cycles);
        $fclose(file_meta);
        
        $display("Test completed successfully");
        $display("Results written to sim/sim_diag_out.txt and sim/sim_meta.txt");
        
        $finish;
    end
    
    // Simulation timeout watchdog
    initial begin
        #(CLK_PERIOD * TIMEOUT * 2);
        $display("ERROR: Absolute simulation timeout reached");
        $finish;
    end

endmodule
