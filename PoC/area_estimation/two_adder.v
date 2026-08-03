// Ground truth: exactly two independent 16-bit adders -- should be
// approximately 2x the cell count of one_adder.v, since the adders are
// unrelated (no shared logic for yosys to fold together).
module two_adder (
    input  wire [15:0] a, b, c, d,
    output wire [15:0] sum1,
    output wire [15:0] sum2
);
    assign sum1 = a + b;
    assign sum2 = c + d;
endmodule
