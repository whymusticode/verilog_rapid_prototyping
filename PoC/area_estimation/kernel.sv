`timescale 1ns/1ps
`include "kernel.h.sv"

module kernel_top (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    output reg         busy,
    output reg         done,
    // a[0..3]: 4 elements x 17 bits = 68 bits
    input  wire signed [(`DIM_IN0_0 * `W_IN0)-1:0] in0,
    // b[0..3]: 4 elements x 17 bits = 68 bits
    input  wire signed [(`DIM_IN1_0 * `W_IN1)-1:0] in1,
    // out: scalar 25 bits
    output reg  signed [`W_OUT0-1:0] out0
);

    // FSM states
    localparam S_IDLE = 1'b0;
    localparam S_DONE = 1'b1;

    reg state;

    // Extract individual elements combinationally
    wire signed [`W_IN0-1:0] a0 = in0[0*`W_IN0 +: `W_IN0];
    wire signed [`W_IN0-1:0] a1 = in0[1*`W_IN0 +: `W_IN0];
    wire signed [`W_IN0-1:0] a2 = in0[2*`W_IN0 +: `W_IN0];
    wire signed [`W_IN0-1:0] a3 = in0[3*`W_IN0 +: `W_IN0];

    wire signed [`W_IN1-1:0] b0 = in1[0*`W_IN1 +: `W_IN1];
    wire signed [`W_IN1-1:0] b1 = in1[1*`W_IN1 +: `W_IN1];
    wire signed [`W_IN1-1:0] b2 = in1[2*`W_IN1 +: `W_IN1];
    wire signed [`W_IN1-1:0] b3 = in1[3*`W_IN1 +: `W_IN1];

    // All 4 products computed combinationally (17*17=34 bits)
    wire signed [33:0] p0 = a0 * b0;
    wire signed [33:0] p1 = a1 * b1;
    wire signed [33:0] p2 = a2 * b2;
    wire signed [33:0] p3 = a3 * b3;

    // Sum of 4 products: 34 bits + 2 bits overhead = 36 bits
    wire signed [35:0] sum = {{2{p0[33]}}, p0} + {{2{p1[33]}}, p1} +
                             {{2{p2[33]}}, p2} + {{2{p3[33]}}, p3};

    // Result: sum is Q16 (product of two Q8 values), shift right by 8 to get Q8
    // sum is 36 bits; output is 25 bits signed; take bits [32:8]
    wire signed [24:0] result = sum[32:8];

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            busy  <= 1'b0;
            done  <= 1'b0;
            out0  <= '0;
        end else begin
            done <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (start) begin
                        busy  <= 1'b1;
                        state <= S_DONE;
                    end
                end

                S_DONE: begin
                    out0  <= result;
                    done  <= 1'b1;
                    busy  <= 1'b0;
                    state <= S_IDLE;
                end

                default: begin
                    state <= S_IDLE;
                    busy  <= 1'b0;
                    done  <= 1'b0;
                end
            endcase
        end
    end

endmodule
