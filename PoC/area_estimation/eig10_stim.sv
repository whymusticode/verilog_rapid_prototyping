// Synthesizable-only stimulus for yosys `sim -clock clk -reset rst -n N`.
// Same dense non-converging matrix fill as PoC/vivado_vs_iverilog/eig10's
// bench_tb.sv (no `real`/file-I/O, which yosys's frontend rejects), so the
// FSM does sustained real work for the full cycle budget instead of idling.
`include "eig10_kernel.h.sv"

module stim_top (
    input  wire clk,
    input  wire rst
);
    reg start = 0;
    wire busy, done;
    reg  signed [`DIM_IN0_0*`DIM_IN0_1*2*`ACM_W-1:0] in0;
    reg  [`ITER_W-1:0] in1;
    wire signed [`DIM_OUT0_0*2*`EIG_W-1:0] out0;
    wire signed [`DIM_OUT1_0*`DIM_OUT1_1*2*`EIG_W-1:0] out1;
    wire [`ITER_W-1:0] out2;

    integer r2, c2;
    initial begin
        in0 = 0;
        for (r2 = 0; r2 < 10; r2 = r2 + 1)
            in0[((r2*10+r2)*2)*`ACM_W +: `ACM_W] = (r2 + 1) << 10;
        for (r2 = 0; r2 < 10; r2 = r2 + 1)
            for (c2 = r2 + 1; c2 < 10; c2 = c2 + 1) begin
                in0[((r2*10+c2)*2)*`ACM_W +: `ACM_W] = 100 + r2*10 + c2;
                in0[((c2*10+r2)*2)*`ACM_W +: `ACM_W] = 100 + r2*10 + c2;
            end
        in1 = 2000;
    end

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
        .in0(in0), .in1(in1), .out0(out0), .out1(out1), .out2(out2)
    );
endmodule
