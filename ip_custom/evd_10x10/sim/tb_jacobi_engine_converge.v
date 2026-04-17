`timescale 1ns/1ps
module tb_jacobi_engine_converge;
  localparam integer N = 10;
  localparam integer W = 23;

  reg clk = 0;
  reg rst = 1;
  reg start = 0;
  reg [15:0] max_iter = 512;
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
  integer fd_in;
  integer fd_meta;
  integer r;
  integer in_re;
  integer in_im;

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
    fd_meta = $fopen("evd_10x10/sim/sim_meta_converge.txt", "w");
    $fwrite(fd_meta, "iter_count %0d\n", iter_count);
    $fclose(fd_meta);
    $display("TB converge iter_count=%0d", iter_count);
    $finish;
  end
endmodule
