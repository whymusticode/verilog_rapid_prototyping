// Synthesizable-only stimulus wrapper for yosys `sim` (no file I/O / `real`,
// which yosys's frontend rejects -- clk/rst are driven by `sim -clock/-reset`
// itself, this just ties off start/inputs to fixed values).
`include "kernel.h.sv"

module stim_top (
    input  wire clk,
    input  wire rst
);
    reg start = 0;
    wire busy, done;
    wire signed [(`DIM_IN0_0*`W_IN0)-1:0] in0 = {4{17'sd100}};
    wire signed [(`DIM_IN1_0*`W_IN1)-1:0] in1 = {4{17'sd50}};
    wire signed [`W_OUT0-1:0] out0;

    reg [3:0] cnt = 0;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 0;
            start <= 0;
        end else if (cnt == 1) begin
            start <= 1;
            cnt <= cnt + 1;
        end else begin
            start <= 0;
            if (cnt < 15) cnt <= cnt + 1;
        end
    end

    kernel_top uut (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .in0(in0), .in1(in1), .out0(out0)
    );
endmodule
