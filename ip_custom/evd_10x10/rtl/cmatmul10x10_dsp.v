`timescale 1ns/1ps
module cmatmul10x10_dsp #(
  parameter integer N = 10,
  parameter integer W = 23,
  parameter integer ACC_GUARD = 8,
  parameter integer NUM_DSP = 30
) (
  input  wire clk,
  input  wire rst,
  input  wire start,
  input  wire signed [N*N*W-1:0] a_re_flat,
  input  wire signed [N*N*W-1:0] a_im_flat,
  input  wire signed [N*N*W-1:0] b_re_flat,
  input  wire signed [N*N*W-1:0] b_im_flat,
  output reg  signed [N*N*(2*W+ACC_GUARD)-1:0] c_re_flat,
  output reg  signed [N*N*(2*W+ACC_GUARD)-1:0] c_im_flat,
  output reg busy,
  output reg done
);
  localparam integer CW = 2*W + ACC_GUARD;
  localparam integer PAR_CMUL = (NUM_DSP < 3) ? 1 : (NUM_DSP / 3);

  reg [3:0] i_idx;
  reg [3:0] j_idx;
  reg [4:0] k_idx;
  reg signed [CW-1:0] acc_re;
  reg signed [CW-1:0] acc_im;

  integer lane;
  integer k_l;
  integer dst_idx;
  integer src_a_idx;
  integer src_b_idx;

  reg signed [CW-1:0] delta_re;
  reg signed [CW-1:0] delta_im;
  reg signed [W-1:0] ar;
  reg signed [W-1:0] ai;
  reg signed [W-1:0] br;
  reg signed [W-1:0] bi;
  reg signed [2*W+1:0] pr;
  reg signed [2*W+1:0] pi;

  always @(posedge clk) begin
    if (rst) begin
      busy <= 1'b0;
      done <= 1'b0;
      i_idx <= 0;
      j_idx <= 0;
      k_idx <= 0;
      acc_re <= 0;
      acc_im <= 0;
      c_re_flat <= 0;
      c_im_flat <= 0;
    end else begin
      done <= 1'b0;

      if (start && !busy) begin
        busy <= 1'b1;
        i_idx <= 0;
        j_idx <= 0;
        k_idx <= 0;
        acc_re <= 0;
        acc_im <= 0;
      end else if (busy) begin
        delta_re = 0;
        delta_im = 0;

        for (lane = 0; lane < PAR_CMUL; lane = lane + 1) begin
          k_l = k_idx + lane;
          if (k_l < N) begin
            src_a_idx = i_idx * N + k_l;
            src_b_idx = k_l * N + j_idx;

            ar = a_re_flat[src_a_idx*W +: W];
            ai = a_im_flat[src_a_idx*W +: W];
            br = b_re_flat[src_b_idx*W +: W];
            bi = b_im_flat[src_b_idx*W +: W];

            pr = (ar * br) - (ai * bi);
            pi = ((ar + ai) * (br + bi)) - (ar * br) - (ai * bi);

            delta_re = delta_re + $signed({{(CW-(2*W+2)){pr[2*W+1]}}, pr});
            delta_im = delta_im + $signed({{(CW-(2*W+2)){pi[2*W+1]}}, pi});
          end
        end

        acc_re <= acc_re + delta_re;
        acc_im <= acc_im + delta_im;

        if (k_idx + PAR_CMUL >= N) begin
          dst_idx = i_idx * N + j_idx;
          c_re_flat[dst_idx*CW +: CW] <= acc_re + delta_re;
          c_im_flat[dst_idx*CW +: CW] <= acc_im + delta_im;
          acc_re <= 0;
          acc_im <= 0;
          k_idx <= 0;

          if (j_idx == N-1) begin
            j_idx <= 0;
            if (i_idx == N-1) begin
              i_idx <= 0;
              busy <= 1'b0;
              done <= 1'b1;
            end else begin
              i_idx <= i_idx + 1'b1;
            end
          end else begin
            j_idx <= j_idx + 1'b1;
          end
        end else begin
          k_idx <= k_idx + PAR_CMUL[4:0];
        end
      end
    end
  end
endmodule
