`ifndef KERNEL_H_SV
`define KERNEL_H_SV

// Input a: shape [4], width = bits(16) + signed(1) = 17
`define DIM_IN0_0 4

// Input b: shape [4], width = bits(16) + signed(1) = 17
`define DIM_IN1_0 4

// Output out: scalar, no dimension macros needed

// Port widths
`define W_IN0  17
`define W_IN1  17
`define W_OUT0 25

`endif // KERNEL_H_SV
