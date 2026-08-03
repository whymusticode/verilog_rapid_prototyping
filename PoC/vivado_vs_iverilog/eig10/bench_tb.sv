// Fixed-N-cycle benchmark testbench: drives the real eig_10 kernel with
// zeroed inputs and runs exactly N_CYCLES clock edges (never waits for
// `done` -- eig_10's real max_iter=2000 run is too slow for iverilog to
// finish in reasonable wall time; see PoC/vivado_vs_iverilog/README).
// Both simulators run the identical bounded workload so wall-clock time
// is directly comparable.
`timescale 1ns/1ps
`include "kernel.h.sv"

module bench_tb;
    localparam N_CYCLES = 200000;

    reg clk = 0;
    reg rst = 1;
    reg start = 0;
    wire busy, done;

    reg  signed [`DIM_IN0_0*`DIM_IN0_1*2*`ACM_W-1:0] in0;
    reg  [`ITER_W-1:0] in1;
    wire signed [`DIM_OUT0_0*2*`EIG_W-1:0] out0;
    wire signed [`DIM_OUT1_0*`DIM_OUT1_1*2*`EIG_W-1:0] out1;
    wire [`ITER_W-1:0] out2;

    integer i;

    kernel_top uut (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .in0(in0), .in1(in1), .out0(out0), .out1(out1), .out2(out2)
    );

    always #2.5 clk = ~clk;   // 200 MHz, matches params.yaml

    initial begin
        // Fully dense, non-degenerate Hermitian-ish input: every off-diagonal
        // pair nonzero so pivot search never finds off_diag_max < THRESH --
        // the FSM must keep running real sweeps for the full N_CYCLES budget
        // instead of converging after 1-2 sweeps and idling. This is what
        // makes the benchmark measure sustained simulation throughput rather
        // than mostly fixed per-run overhead.
        in0 = 0;
        for (i = 0; i < 10; i = i + 1)
            in0[((i*10+i)*2)*`ACM_W +: `ACM_W] = (i + 1) << 10;
        begin : offdiag
            integer r2, c2;
            for (r2 = 0; r2 < 10; r2 = r2 + 1)
                for (c2 = r2 + 1; c2 < 10; c2 = c2 + 1) begin
                    in0[((r2*10+c2)*2)*`ACM_W +: `ACM_W] = 100 + r2*10 + c2;
                    in0[((c2*10+r2)*2)*`ACM_W +: `ACM_W] = 100 + r2*10 + c2;
                end
        end
        in1 = 2000;

        @(negedge clk); rst = 0;
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;

        repeat (N_CYCLES) @(posedge clk);

        $display("BENCH_DONE cycles=%0d busy=%0d done=%0d iter_z=%0d state=%0d out2=%0d", N_CYCLES, busy, done, uut.iter_z, uut.state, out2);
        $finish;
    end
endmodule
