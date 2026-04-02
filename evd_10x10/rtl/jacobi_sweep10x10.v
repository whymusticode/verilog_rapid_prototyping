`timescale 1ns/1ps
module jacobi_sweep10x10 #(
  parameter integer N = 10,
  parameter integer W = 23,
  parameter integer Q = 20
) (
  input  wire clk,
  input  wire rst,
  input  wire start,
  input  wire signed [N*N*W-1:0] a_re_in,
  input  wire signed [N*N*W-1:0] a_im_in,
  input  wire signed [N*N*W-1:0] v_re_in,
  input  wire signed [N*N*W-1:0] v_im_in,
  output reg  signed [N*N*W-1:0] a_re_out,
  output reg  signed [N*N*W-1:0] a_im_out,
  output reg  signed [N*N*W-1:0] v_re_out,
  output reg  signed [N*N*W-1:0] v_im_out,
  output reg  [31:0] pivot_mag_out,
  output reg  [5:0] pair_count,
  output reg busy,
  output reg done
);
  localparam [3:0] S_IDLE      = 4'd0;
  localparam [3:0] S_LOAD      = 4'd1;
  localparam [3:0] S_FIND_INIT = 4'd2;
  localparam [3:0] S_FIND_SCAN = 4'd3;
  localparam [3:0] S_COEF      = 4'd4;
  localparam [3:0] S_DIAG      = 4'd5;
  localparam [3:0] S_UPD_A     = 4'd6;
  localparam [3:0] S_UPD_V     = 4'd7;
  localparam [3:0] S_PACK      = 4'd8;
  localparam [3:0] S_DONE      = 4'd9;

  reg [3:0] state;
  integer i_idx;
  integer j_idx;
  integer k_idx;
  integer idx;
  integer p_idx;
  integer q_idx;

  reg [63:0] max_mag_sq;
  reg [63:0] mag_sq;
  reg [31:0] apq_mag;
  reg signed [31:0] app_i;
  reg signed [31:0] aqq_i;
  reg signed [31:0] apq_re_i;
  reg signed [31:0] apq_im_i;
  reg signed [31:0] cp_q;
  reg signed [31:0] sp_q;
  reg signed [31:0] r_q;
  reg signed [31:0] t_q;
  reg signed [31:0] c_q;
  reg signed [31:0] s_q;
  reg signed [31:0] den_t;
  reg [31:0] sqrt_term_q;
  reg signed [31:0] delta_i;
  reg signed [31:0] c2_q;
  reg signed [31:0] s2_q;
  reg signed [31:0] cs2_q;
  reg signed [63:0] num64;

  reg signed [63:0] xr;
  reg signed [63:0] xi;
  reg signed [63:0] yr;
  reg signed [63:0] yi;
  reg signed [63:0] tr1;
  reg signed [63:0] ti1;
  reg signed [63:0] tr2;
  reg signed [63:0] ti2;
  reg signed [63:0] nr;
  reg signed [63:0] ni;
  reg signed [63:0] n2r;
  reg signed [63:0] n2i;
  reg signed [63:0] diag_p;
  reg signed [63:0] diag_q;
  reg signed [63:0] bmag;

  reg signed [W-1:0] A_re [0:N-1][0:N-1];
  reg signed [W-1:0] A_im [0:N-1][0:N-1];
  reg signed [W-1:0] V_re [0:N-1][0:N-1];
  reg signed [W-1:0] V_im [0:N-1][0:N-1];

  function automatic signed [W-1:0] clampw(input signed [63:0] x);
    reg signed [63:0] maxv;
    reg signed [63:0] minv;
    begin
      maxv = (64'sd1 <<< (W-1)) - 1;
      minv = -(64'sd1 <<< (W-1));
      if (x > maxv) clampw = maxv[W-1:0];
      else if (x < minv) clampw = minv[W-1:0];
      else clampw = x[W-1:0];
    end
  endfunction

  function automatic signed [31:0] abs32(input signed [31:0] x);
    begin
      if (x < 0) abs32 = -x;
      else abs32 = x;
    end
  endfunction

  function automatic [31:0] isqrt64(input [63:0] x);
    reg [63:0] op;
    reg [63:0] res;
    reg [63:0] one;
    integer n;
    begin
      op = x;
      res = 0;
      one = 64'h4000000000000000;
      for (n = 0; n < 32; n = n + 1) begin
        if (one > op) one = one >> 2;
      end
      for (n = 0; n < 32; n = n + 1) begin
        if (one != 0) begin
          if (op >= (res + one)) begin
            op = op - (res + one);
            res = (res >> 1) + one;
          end else begin
            res = res >> 1;
          end
          one = one >> 2;
        end
      end
      isqrt64 = res[31:0];
    end
  endfunction

  function automatic signed [31:0] qmul(input signed [31:0] a, input signed [31:0] b);
    reg signed [63:0] t;
    begin
      t = a * b;
      if (t >= 0) qmul = (t + (64'sd1 << (Q-1))) >>> Q;
      else qmul = -(((-t) + (64'sd1 << (Q-1))) >>> Q);
    end
  endfunction

  function automatic signed [31:0] clamp_unit_q(input signed [31:0] x);
    reg signed [31:0] lim;
    begin
      lim = (32'sd1 <<< Q);
      if (x > lim) clamp_unit_q = lim;
      else if (x < -lim) clamp_unit_q = -lim;
      else clamp_unit_q = x;
    end
  endfunction

  always @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE;
      pair_count <= 0;
      busy <= 1'b0;
      done <= 1'b0;
      pivot_mag_out <= 32'd0;
      a_re_out <= 0;
      a_im_out <= 0;
      v_re_out <= 0;
      v_im_out <= 0;
      i_idx <= 0;
      j_idx <= 0;
      k_idx <= 0;
      p_idx <= 0;
      q_idx <= 1;
      max_mag_sq <= 0;
    end else begin
      done <= 1'b0;
      case (state)
        S_IDLE: begin
          if (start) begin
            busy <= 1'b1;
            i_idx <= 0;
            j_idx <= 0;
            state <= S_LOAD;
          end
        end

        S_LOAD: begin
          idx = i_idx * N + j_idx;
          A_re[i_idx][j_idx] <= $signed(a_re_in[idx*W +: W]);
          A_im[i_idx][j_idx] <= $signed(a_im_in[idx*W +: W]);
          V_re[i_idx][j_idx] <= $signed(v_re_in[idx*W +: W]);
          V_im[i_idx][j_idx] <= $signed(v_im_in[idx*W +: W]);
          if (j_idx == N-1) begin
            j_idx <= 0;
            if (i_idx == N-1) begin
              i_idx <= 0;
              state <= S_FIND_INIT;
            end else begin
              i_idx <= i_idx + 1;
            end
          end else begin
            j_idx <= j_idx + 1;
          end
        end

        S_FIND_INIT: begin
          i_idx <= 0;
          j_idx <= 1;
          p_idx <= 0;
          q_idx <= 1;
          max_mag_sq <= 0;
          pair_count <= 0;
          state <= S_FIND_SCAN;
        end

        S_FIND_SCAN: begin
          app_i = A_re[i_idx][j_idx];
          aqq_i = A_im[i_idx][j_idx];
          mag_sq = app_i * app_i + aqq_i * aqq_i;
          if (mag_sq > max_mag_sq) begin
            max_mag_sq <= mag_sq;
            p_idx <= i_idx;
            q_idx <= j_idx;
          end
          if (j_idx == N-1) begin
            if (i_idx == N-2) begin
              state <= S_COEF;
            end else begin
              i_idx <= i_idx + 1;
              j_idx <= i_idx + 2;
            end
          end else begin
            j_idx <= j_idx + 1;
          end
        end

        S_COEF: begin
          apq_mag = isqrt64(max_mag_sq);
          pivot_mag_out <= apq_mag;
          if (apq_mag != 0) begin
            app_i = A_re[p_idx][p_idx];
            aqq_i = A_re[q_idx][q_idx];
            apq_re_i = A_re[p_idx][q_idx];
            apq_im_i = A_im[p_idx][q_idx];
            num64 = $signed(apq_re_i);
            cp_q = clamp_unit_q((num64 <<< Q) / $signed({1'b0, apq_mag}));
            num64 = $signed(apq_im_i);
            sp_q = clamp_unit_q(-((num64 <<< Q) / $signed({1'b0, apq_mag})));
            delta_i = $signed(app_i) - $signed(aqq_i);
            if (delta_i == 0) begin
              t_q = (32'sd1 <<< Q);
            end else begin
              num64 = $signed({1'b0, apq_mag});
              r_q = (num64 <<< (Q+1)) / delta_i;
              sqrt_term_q = isqrt64((r_q * r_q) + (64'sd1 <<< (2*Q)));
              den_t = (32'sd1 <<< Q) + $signed({1'b0, sqrt_term_q});
              if (den_t != 0) begin
                num64 = $signed(r_q);
                t_q = clamp_unit_q((num64 <<< Q) / den_t);
              end
              else t_q = 0;
            end
            c_q = clamp_unit_q((64'sd1 <<< (2*Q)) / isqrt64((t_q * t_q) + (64'sd1 <<< (2*Q))));
            s_q = clamp_unit_q(qmul(t_q, c_q));
          end
          state <= S_DIAG;
        end

        S_DIAG: begin
          c2_q = qmul(c_q, c_q);
          s2_q = qmul(s_q, s_q);
          cs2_q = qmul(c_q, s_q) <<< 1;
          bmag = apq_mag;
          diag_p = qmul(c2_q, app_i) + qmul(s2_q, aqq_i) + qmul(cs2_q, bmag);
          diag_q = qmul(s2_q, app_i) + qmul(c2_q, aqq_i) - qmul(cs2_q, bmag);
          A_re[p_idx][p_idx] <= clampw(diag_p);
          A_im[p_idx][p_idx] <= 0;
          A_re[q_idx][q_idx] <= clampw(diag_q);
          A_im[q_idx][q_idx] <= 0;
          A_re[p_idx][q_idx] <= 0;
          A_im[p_idx][q_idx] <= 0;
          A_re[q_idx][p_idx] <= 0;
          A_im[q_idx][p_idx] <= 0;
          k_idx <= 0;
          state <= S_UPD_A;
        end

        S_UPD_A: begin
          if (k_idx != p_idx && k_idx != q_idx) begin
            xr = A_re[k_idx][p_idx];
            xi = A_im[k_idx][p_idx];
            yr = A_re[k_idx][q_idx];
            yi = A_im[k_idx][q_idx];
            tr1 = qmul(yr, cp_q) - qmul(yi, sp_q);
            ti1 = qmul(yr, sp_q) + qmul(yi, cp_q);
            tr2 = qmul(xr, cp_q) + qmul(xi, sp_q);
            ti2 = -qmul(xr, sp_q) + qmul(xi, cp_q);
            nr  = qmul(c_q, xr) + qmul(s_q, tr1);
            ni  = qmul(c_q, xi) + qmul(s_q, ti1);
            n2r = qmul(s_q, tr2) - qmul(c_q, yr);
            n2i = qmul(s_q, ti2) - qmul(c_q, yi);
            A_re[k_idx][p_idx] <= clampw(nr);
            A_im[k_idx][p_idx] <= clampw(ni);
            A_re[p_idx][k_idx] <= clampw(nr);
            A_im[p_idx][k_idx] <= clampw(-ni);
            A_re[k_idx][q_idx] <= clampw(n2r);
            A_im[k_idx][q_idx] <= clampw(n2i);
            A_re[q_idx][k_idx] <= clampw(n2r);
            A_im[q_idx][k_idx] <= clampw(-n2i);
          end
          if (k_idx == N-1) begin
            k_idx <= 0;
            state <= S_UPD_V;
          end else begin
            k_idx <= k_idx + 1;
          end
        end

        S_UPD_V: begin
          xr = V_re[k_idx][p_idx];
          xi = V_im[k_idx][p_idx];
          yr = V_re[k_idx][q_idx];
          yi = V_im[k_idx][q_idx];
          tr1 = qmul(yr, cp_q) - qmul(yi, sp_q);
          ti1 = qmul(yr, sp_q) + qmul(yi, cp_q);
          tr2 = qmul(xr, cp_q) + qmul(xi, sp_q);
          ti2 = -qmul(xr, sp_q) + qmul(xi, cp_q);
          nr  = qmul(c_q, xr) + qmul(s_q, tr1);
          ni  = qmul(c_q, xi) + qmul(s_q, ti1);
          n2r = qmul(s_q, tr2) - qmul(c_q, yr);
          n2i = qmul(s_q, ti2) - qmul(c_q, yi);
          V_re[k_idx][p_idx] <= clampw(nr);
          V_im[k_idx][p_idx] <= clampw(ni);
          V_re[k_idx][q_idx] <= clampw(n2r);
          V_im[k_idx][q_idx] <= clampw(n2i);
          if (k_idx == N-1) begin
            i_idx <= 0;
            j_idx <= 0;
            state <= S_PACK;
          end else begin
            k_idx <= k_idx + 1;
          end
        end

        S_PACK: begin
          idx = i_idx * N + j_idx;
          a_re_out[idx*W +: W] <= A_re[i_idx][j_idx];
          a_im_out[idx*W +: W] <= A_im[i_idx][j_idx];
          v_re_out[idx*W +: W] <= V_re[i_idx][j_idx];
          v_im_out[idx*W +: W] <= V_im[i_idx][j_idx];
          if (j_idx == N-1) begin
            j_idx <= 0;
            if (i_idx == N-1) begin
              state <= S_DONE;
            end else begin
              i_idx <= i_idx + 1;
            end
          end else begin
            j_idx <= j_idx + 1;
          end
        end

        S_DONE: begin
          busy <= 1'b0;
          done <= 1'b1;
          state <= S_IDLE;
        end

        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
