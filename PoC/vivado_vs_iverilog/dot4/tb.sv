`define DIM_IN0_0 4
`define DIM_IN1_0 4

`timescale 1ns/1ps
`include "kernel.h.sv"

module tb;
    localparam IO_DIR  = "/home/mbenton/verilog_rapid_prototyping/conversion_026/dot4_io/";
    localparam SIM_DIR = "/home/mbenton/verilog_rapid_prototyping/conversion_026/build/sim/";

    reg clk = 0;
    reg rst = 1;
    reg start = 0;
    wire busy, done;

    integer fd, r, idx_i;
    real rv, iv;
    reg [63:0] cycle_count;

    reg  signed [67:0] in0;
    reg  signed [67:0] in1;
    wire signed [24:0] out0;

    always #5.000000 clk = ~clk;

    kernel_top uut (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .in0(in0), .in1(in1), .out0(out0)
    );

    always @(posedge clk) begin
        if (rst) cycle_count <= 0;
        else if (busy) cycle_count <= cycle_count + 1;
    end

    initial begin
        cycle_count = 0;
            fd = $fopen({IO_DIR, "in_a.txt"}, "r");
            if (fd == 0) begin $display("Cannot open in_a.txt"); $finish; end
            for (idx_i = 0; idx_i < 4; idx_i = idx_i + 1) begin
                r = $fscanf(fd, "%f", rv);
                in0[(idx_i+1)*17-1 -: 17] = $rtoi(rv * real'(256));
            end
            $fclose(fd);
            fd = $fopen({IO_DIR, "in_b.txt"}, "r");
            if (fd == 0) begin $display("Cannot open in_b.txt"); $finish; end
            for (idx_i = 0; idx_i < 4; idx_i = idx_i + 1) begin
                r = $fscanf(fd, "%f", rv);
                in1[(idx_i+1)*17-1 -: 17] = $rtoi(rv * real'(256));
            end
            $fclose(fd);

        @(negedge clk); rst = 0;
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;

        wait (done);
        @(negedge clk);

        if (cycle_count == 0) begin
            $display("CHEAT: busy was never asserted between start and done -- clock_cycles must be >= 1");
            $finish;
        end

            fd = $fopen({SIM_DIR, "out.txt"}, "w");
            if (fd == 0) begin $display("Cannot open out.txt"); $finish; end
            $fwrite(fd, "%.17g\n", real'($signed(out0)) / real'(256));
            $fclose(fd);

        fd = $fopen({SIM_DIR, "clock_cycles.txt"}, "w");
        $fwrite(fd, "%0d\n", cycle_count);
        $fclose(fd);

        $display("SIM_DONE cycle_count=%0d", cycle_count);
        $finish;
    end
endmodule
