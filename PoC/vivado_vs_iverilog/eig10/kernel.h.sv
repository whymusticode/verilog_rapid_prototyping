`ifndef KERNEL_H_SV
`define KERNEL_H_SV

// Port widths: bits + signed
// acm: complex, bits=22, signed=1 => component width = 23
// eigenvalues: complex, bits=22, signed=1 => component width = 23
// eigenvectors: complex, bits=22, signed=1 => component width = 23
// ite: bits=16, signed=0 => width = 16
// max_iter: bits=16, signed=0 => width = 16

`define ACM_W       23
`define EIG_W       23
`define ITER_W      16

// in0 = A (acm): shape [10,10], complex => 10*10*2*23 bits
`define DIM_IN0_0   10
`define DIM_IN0_1   10

// in1 = max_iter: scalar, no dim macros needed

// out0 = eigenvalues: shape [10], complex => 10*2*23 bits
`define DIM_OUT0_0  10

// out1 = eigenvectors: shape [10,10], complex => 10*10*2*23 bits
`define DIM_OUT1_0  10
`define DIM_OUT1_1  10

// out2 = ite: scalar

`endif
