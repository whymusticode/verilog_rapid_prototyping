`timescale 1ns/1ps
module tb_jacobi_engine;
  localparam integer N = 10;
  localparam integer W = 23;

  reg clk = 0;
  reg rst = 1;
  reg start = 0;
  reg [15:0] max_iter = 1;
  reg signed [N*N*W-1:0] a_re_in = 0;
  reg signed [N*N*W-1:0] a_im_in = 0;
  wire signed [N*N*W-1:0] a_re_out;
  wire signed [N*N*W-1:0] a_im_out;
  wire signed [N*N*W-1:0] v_re_out;
  wire signed [N*N*W-1:0] v_im_out;
  wire [15:0] iter_count;
  wire busy;
  wire done;

  jacobi_engine10x10 #(.N(N), .W(W)) dut (
    .clk(clk),
    .rst(rst),
    .start(start),
    .max_iter(max_iter),
    .a_re_in(a_re_in),
    .a_im_in(a_im_in),
    .a_re_out(a_re_out),
    .a_im_out(a_im_out),
    .v_re_out(v_re_out),
    .v_im_out(v_im_out),
    .iter_count(iter_count),
    .busy(busy),
    .done(done)
  );

  always #5 clk = ~clk;

  integer i;
  integer fd;
  integer fd_meta;
  integer fd_dbg;
  integer fd_in;
  integer r;
  integer in_re;
  integer in_im;
  reg signed [W-1:0] d_re;
  reg signed [W-1:0] d_im;
  initial begin
    #30 rst = 0;
    fd_in = $fopen("evd_10x10/sim/tb_input_matrix.txt", "r");
    if (fd_in == 0) begin
      $display("ERROR: missing evd_10x10/sim/tb_input_matrix.txt");
      $finish;
    end
    for (i = 0; i < N*N; i = i + 1) begin
      r = $fscanf(fd_in, "%d %d\n", in_re, in_im);
      if (r != 2) begin
        $display("ERROR: bad matrix input line %0d", i);
        $finish;
      end
      a_re_in[i*W +: W] = in_re[W-1:0];
      a_im_in[i*W +: W] = in_im[W-1:0];
    end
    $fclose(fd_in);
    #20 start = 1;
    #10 start = 0;
    wait(done);
    fd = $fopen("evd_10x10/sim/sim_diag_out.txt", "w");
    for (i = 0; i < N; i = i + 1) begin
      d_re = a_re_out[(i*N+i)*W +: W];
      d_im = a_im_out[(i*N+i)*W +: W];
      $fwrite(fd, "%0d %0d\n", d_re, d_im);
    end
    $fclose(fd);
    fd_dbg = $fopen("evd_10x10/sim/sim_intermediates.txt", "w");
    $fwrite(fd_dbg, "p %0d\n", dut.u_sweep.p_idx);
    $fwrite(fd_dbg, "q %0d\n", dut.u_sweep.q_idx);
    $fwrite(fd_dbg, "apq_mag %0d\n", dut.u_sweep.apq_mag);
    $fwrite(fd_dbg, "app_i %0d\n", dut.u_sweep.app_i);
    $fwrite(fd_dbg, "aqq_i %0d\n", dut.u_sweep.aqq_i);
    $fwrite(fd_dbg, "apq_re_i %0d\n", dut.u_sweep.apq_re_i);
    $fwrite(fd_dbg, "apq_im_i %0d\n", dut.u_sweep.apq_im_i);
    $fwrite(fd_dbg, "cp_q %0d\n", dut.u_sweep.cp_q);
    $fwrite(fd_dbg, "sp_q %0d\n", dut.u_sweep.sp_q);
    $fwrite(fd_dbg, "r_q %0d\n", dut.u_sweep.r_q);
    $fwrite(fd_dbg, "t_q %0d\n", dut.u_sweep.t_q);
    $fwrite(fd_dbg, "c_q %0d\n", dut.u_sweep.c_q);
    $fwrite(fd_dbg, "s_q %0d\n", dut.u_sweep.s_q);
    $fwrite(fd_dbg, "diag_p %0d\n", dut.u_sweep.diag_p);
    $fwrite(fd_dbg, "diag_q %0d\n", dut.u_sweep.diag_q);
    $fclose(fd_dbg);
    fd_meta = $fopen("evd_10x10/sim/sim_meta.txt", "w");
    $fwrite(fd_meta, "iter_count %0d\n", iter_count);
    $fclose(fd_meta);
    $display("TB done iter_count=%0d", iter_count);
    $finish;
  end
endmodule
