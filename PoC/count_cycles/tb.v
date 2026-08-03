// Minimal testbench: real clock, real cycle counter gated on `busy`,
// proves iverilog can produce a genuine clock-cycle count (not a proxy).
`timescale 1ns/1ps

module tb;
    reg clk = 0;
    reg rst = 1;
    reg start = 0;
    wire busy, done;

    reg [63:0] cycle_count = 0;

    dut #(.N(5)) uut (
        .clk(clk), .rst(rst), .start(start),
        .busy(busy), .done(done)
    );

    always #5 clk = ~clk;   // 100 MHz

    always @(posedge clk) begin
        if (busy) cycle_count <= cycle_count + 1;
    end

    initial begin
        @(negedge clk); rst = 0;
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;

        wait (done);
        @(negedge clk);   // settle

        $display("cycle_count=%0d", cycle_count);
        if (cycle_count == 5)
            $display("PASS");
        else
            $display("FAIL: expected 5, got %0d", cycle_count);

        $finish;
    end
endmodule
