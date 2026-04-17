`timescale 1ns/1ps
module jacobi_engine10x10 #(
  parameter integer N = 10,
  parameter integer W = 23,
  parameter integer CONV_THRESH = 64
) (
  input  wire clk,
  input  wire rst,
  input  wire start,
  input  wire [15:0] max_iter,
  input  wire signed [N*N*W-1:0] a_re_in,
  input  wire signed [N*N*W-1:0] a_im_in,
  output wire signed [N*N*W-1:0] a_re_out,
  output wire signed [N*N*W-1:0] a_im_out,
  output wire signed [N*N*W-1:0] v_re_out,
  output wire signed [N*N*W-1:0] v_im_out,
  output reg  [15:0] iter_count,
  output reg busy,
  output reg done
);
  localparam [1:0] S_IDLE = 2'd0;
  localparam [1:0] S_RUN = 2'd1;
  localparam [1:0] S_WAIT = 2'd2;

  reg [1:0] state;
  reg sweep_start;
  wire sweep_done;
  wire [31:0] sweep_pivot_mag;
  reg signed [N*N*W-1:0] a_re_reg;
  reg signed [N*N*W-1:0] a_im_reg;
  reg signed [N*N*W-1:0] v_re_reg;
  reg signed [N*N*W-1:0] v_im_reg;

  wire signed [N*N*W-1:0] sweep_a_re;
  wire signed [N*N*W-1:0] sweep_a_im;
  wire signed [N*N*W-1:0] sweep_v_re;
  wire signed [N*N*W-1:0] sweep_v_im;

  assign a_re_out = a_re_reg;
  assign a_im_out = a_im_reg;
  assign v_re_out = v_re_reg;
  assign v_im_out = v_im_reg;

  jacobi_sweep10x10 #(.N(N), .W(W)) u_sweep (
    .clk(clk),
    .rst(rst),
    .start(sweep_start),
    .a_re_in(a_re_reg),
    .a_im_in(a_im_reg),
    .v_re_in(v_re_reg),
    .v_im_in(v_im_reg),
    .a_re_out(sweep_a_re),
    .a_im_out(sweep_a_im),
    .v_re_out(sweep_v_re),
    .v_im_out(sweep_v_im),
    .pivot_mag_out(sweep_pivot_mag),
    .pair_count(),
    .busy(),
    .done(sweep_done)
  );

  integer d;
  always @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE;
      sweep_start <= 1'b0;
      iter_count <= 0;
      busy <= 1'b0;
      done <= 1'b0;
      a_re_reg <= 0;
      a_im_reg <= 0;
      v_re_reg <= 0;
      v_im_reg <= 0;
      for (d = 0; d < N; d = d + 1) begin
        v_re_reg[(d*N + d)*W +: W] <= {{(W-1){1'b0}}, 1'b1};
      end
    end else begin
      done <= 1'b0;
      sweep_start <= 1'b0;
      case (state)
        S_IDLE: begin
          if (start) begin
            a_re_reg <= a_re_in;
            a_im_reg <= a_im_in;
            v_re_reg <= 0;
            v_im_reg <= 0;
            for (d = 0; d < N; d = d + 1) begin
              v_re_reg[(d*N + d)*W +: W] <= {{(W-1){1'b0}}, 1'b1};
            end
            iter_count <= 0;
            busy <= 1'b1;
            state <= S_RUN;
          end
        end

        S_RUN: begin
          sweep_start <= 1'b1;
          state <= S_WAIT;
        end

        S_WAIT: begin
          if (sweep_done) begin
            a_re_reg <= sweep_a_re;
            a_im_reg <= sweep_a_im;
            v_re_reg <= sweep_v_re;
            v_im_reg <= sweep_v_im;
            iter_count <= iter_count + 1'b1;
            if ((iter_count + 1'b1 >= max_iter) || (sweep_pivot_mag <= CONV_THRESH)) begin
              busy <= 1'b0;
              done <= 1'b1;
              state <= S_IDLE;
            end else begin
              state <= S_RUN;
            end
          end
        end

        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
