`timescale 1ns/1ps
module complex_mul_3dsp #(
  parameter integer W = 23
) (
  input  wire signed [W-1:0] a_re,
  input  wire signed [W-1:0] a_im,
  input  wire signed [W-1:0] b_re,
  input  wire signed [W-1:0] b_im,
  output wire signed [2*W+1:0] p_re,
  output wire signed [2*W+1:0] p_im
);
  wire signed [W:0] a_sum = a_re + a_im;
  wire signed [W:0] b_sum = b_re + b_im;

  wire signed [2*W-1:0] k1 = a_re * b_re;
  wire signed [2*W-1:0] k2 = a_im * b_im;
  wire signed [2*W+1:0] k3 = a_sum * b_sum;

  assign p_re = $signed({{2{k1[2*W-1]}}, k1}) - $signed({{2{k2[2*W-1]}}, k2});
  assign p_im = k3 - $signed({{2{k1[2*W-1]}}, k1}) - $signed({{2{k2[2*W-1]}}, k2});
endmodule
