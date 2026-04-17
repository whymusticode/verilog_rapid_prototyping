// Basys3 wrapper for ZipCPU cordic (ip_submodule/cordic/rtl/cordic.v). SW[15:0]=angle (0..65535 -> 0..2pi).
// btnC = run once; 7-seg shows sin as 0.xxxx. Result valid 18 cycles after submit.
module top (
  input        clk,
  input [15:0] sw,
  input        btnC,
  output [6:0] seg,
  output       dp,
  output [3:0] an,
  output [15:0] led
);
  wire        i_ce = 1'b1;
  wire signed [12:0] i_xval = 13'd4095;
  wire signed [12:0] i_yval = 13'd0;
  wire [19:0] i_phase = { phase_latch[15:0], 4'b0 };
  wire signed [12:0] o_xval, o_yval;
  reg         i_aux;
  wire        o_aux;

  cordic u_cordic (
    .i_clk(clk), .i_reset(rst), .i_ce(i_ce),
    .i_xval(i_xval), .i_yval(i_yval), .i_phase(i_phase),
    .o_xval(o_xval), .o_yval(o_yval), .i_aux(i_aux), .o_aux(o_aux)
  );

  reg rst;
  reg [2:0] rst_cnt;
  reg [3:0] run_cnt;
  reg [15:0] phase_latch;
  initial phase_latch = 16'd0;
  initial run_cnt = 4'd0;
  reg        btnC_prev;
  wire       run_trig = (rst_cnt == 3'd1) || (rst_cnt == 0 && (btnC != btnC_prev));
  reg signed [12:0] sin_r, cos_r;

  initial { rst, rst_cnt } = { 1'b1, 3'd7 };
  always @(posedge clk) begin
    if (rst_cnt) begin rst_cnt <= rst_cnt - 1; rst <= 1; end
    else rst <= 0;
    btnC_prev <= btnC;
    if (run_trig) begin phase_latch <= (rst_cnt == 3'd1) ? 16'd0 : sw; run_cnt <= 4'd19; end
    if (run_cnt != 4'd0) run_cnt <= run_cnt - 1;
    i_aux <= (run_cnt == 4'd19);
    if (run_cnt == 4'd1) begin sin_r <= o_yval; cos_r <= o_xval; end
  end

  // Composable: chain another block here (e.g. sqrt). Add its RTL to build.tcl rtl_libs, then wire and use chain_out for display.
  wire signed [12:0] sin_abs = (sin_r >= 0) ? sin_r : -sin_r;
  wire [31:0] frac = ({{19{1'b0}}, sin_abs} * 32'd10000) / 32'd2385;
  wire [15:0] disp = (frac > 32'd9999) ? 16'd9999 : frac[15:0];
  wire [3:0] d0 = disp / 16'd1000;
  wire [3:0] d1 = (disp / 16'd100) % 4'd10;
  wire [3:0] d2 = (disp / 16'd10) % 4'd10;
  wire [3:0] d3 = disp % 4'd10;

  reg [17:0] ref_cnt;
  reg [1:0] dig_sel_r;
  reg [6:0] seg_r;
  reg [3:0] an_r;
  wire [3:0] dig = (dig_sel_r == 2'd3) ? d0 : (dig_sel_r == 2'd2) ? d1 : (dig_sel_r == 2'd1) ? d2 : d3;

  always @(posedge clk) begin
    ref_cnt <= ref_cnt + 1;
    dig_sel_r <= ref_cnt[17:16];
    case (dig)
      4'd0: seg_r <= 7'b1000000;
      4'd1: seg_r <= 7'b1111001;
      4'd2: seg_r <= 7'b0100100;
      4'd3: seg_r <= 7'b0110000;
      4'd4: seg_r <= 7'b0011001;
      4'd5: seg_r <= 7'b0010010;
      4'd6: seg_r <= 7'b0000010;
      4'd7: seg_r <= 7'b1111000;
      4'd8: seg_r <= 7'b0000000;
      default: seg_r <= 7'b0010000;
    endcase
    an_r <= ~(4'b1 << dig_sel_r);
  end

  assign seg = seg_r;
  assign dp  = 1'b1;
  assign an  = an_r;
  assign led = sw;
endmodule
