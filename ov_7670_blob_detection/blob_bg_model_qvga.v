`timescale 1ns/1ps
module blob_bg_model_qvga #(
    parameter integer IN_W = 640,
    parameter integer IN_H = 480,
    parameter integer DS_LOG2 = 2,           // 640x480 -> 160x120
    parameter integer OUT_W = 160,
    parameter integer OUT_H = 120,
    parameter integer N_PIX = 19200,         // OUT_W * OUT_H
    parameter [7:0] FG_THRESH = 8'd18,
    parameter [7:0] ALPHA_Q8 = 8'd10,        // ~= 0.04
    parameter [7:0] FG_LEAK_Q8 = 8'd1,       // ~= 0.004
    parameter integer GAIN_BETA_SHIFT = 4    // gain settles toward alpha
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  pix_in,
    input  wire        pix_valid,
    input  wire        sof,
    input  wire        eof,
    input  wire [10:0] x_in,
    input  wire [10:0] y_in,
    output reg         fg_valid,
    output reg         fg_bit,
    output reg  [7:0]  fg_x,
    output reg  [6:0]  fg_y,
    output reg         fg_sof,
    output reg         fg_eof,
    output reg  [7:0]  dbg_gain_q8,
    output reg signed [8:0] dbg_illum_bias
);
    localparam integer ADDR_W = 15; // ceil(log2(19200))

    reg [7:0] bg_mem [0:N_PIX-1];
    reg [7:0] gain_q8;
    reg signed [23:0] resid_acc;

    wire sample_en = pix_valid && (x_in[DS_LOG2-1:0] == 0) && (y_in[DS_LOG2-1:0] == 0);
    wire [7:0] x_ds = x_in[10:DS_LOG2];
    wire [6:0] y_ds = y_in[10:DS_LOG2];
    wire [ADDR_W-1:0] addr = y_ds * OUT_W + x_ds;

    reg [7:0] bg_old;
    reg signed [9:0] resid_now;
    reg signed [9:0] resid_illum;
    reg [9:0] abs_resid_illum;
    reg fg_now;
    reg [7:0] k_use;
    reg signed [9:0] delta_bg;
    reg signed [17:0] prod;
    reg signed [10:0] step;
    reg signed [9:0] bg_new_s;
    reg [7:0] bg_new;
    reg signed [15:0] gain_err;
    reg signed [23:0] resid_acc_next;

    integer i;
    always @(posedge clk) begin
        if (rst) begin
            fg_valid <= 1'b0;
            fg_bit <= 1'b0;
            fg_x <= 8'd0;
            fg_y <= 7'd0;
            fg_sof <= 1'b0;
            fg_eof <= 1'b0;
            gain_q8 <= ALPHA_Q8;
            dbg_gain_q8 <= ALPHA_Q8;
            dbg_illum_bias <= 9'sd0;
            resid_acc <= 24'sd0;
            for (i = 0; i < N_PIX; i = i + 1) begin
                bg_mem[i] <= 8'd0;
            end
        end else begin
            fg_valid <= 1'b0;
            fg_sof <= 1'b0;
            fg_eof <= 1'b0;

            if (sample_en) begin
                bg_old = bg_mem[addr];
                resid_now = $signed({2'b00, pix_in}) - $signed({2'b00, bg_old});

                resid_illum = $signed({2'b00, pix_in}) - $signed({2'b00, bg_old}) - dbg_illum_bias;
                abs_resid_illum = resid_illum[9] ? (~resid_illum + 1'b1) : resid_illum;
                fg_now = (abs_resid_illum > FG_THRESH);
                k_use = fg_now ? FG_LEAK_Q8 : gain_q8;

                delta_bg = $signed({2'b00, pix_in}) - $signed({2'b00, bg_old});
                prod = delta_bg * $signed({1'b0, k_use});
                step = prod >>> 8;
                bg_new_s = $signed({2'b00, bg_old}) + step;
                if (bg_new_s < 0) begin
                    bg_new = 8'd0;
                end else if (bg_new_s > 10'd255) begin
                    bg_new = 8'd255;
                end else begin
                    bg_new = bg_new_s[7:0];
                end
                bg_mem[addr] <= bg_new;

                resid_acc_next = (sof ? 24'sd0 : resid_acc) + resid_now;
                resid_acc <= resid_acc_next;

                fg_valid <= 1'b1;
                fg_bit <= fg_now;
                fg_x <= x_ds;
                fg_y <= y_ds;
                fg_sof <= sof;
                fg_eof <= eof;
                if (eof) begin
                    // Coarse divide by ~16384 to estimate global illumination offset.
                    dbg_illum_bias <= resid_acc_next >>> 14;

                    // gain <- gain + beta*(alpha-gain), beta=1/2^GAIN_BETA_SHIFT
                    gain_err = $signed({8'd0, ALPHA_Q8}) - $signed({8'd0, gain_q8});
                    gain_q8 <= gain_q8 + (gain_err >>> GAIN_BETA_SHIFT);
                    dbg_gain_q8 <= gain_q8;
                end
            end else if (sof) begin
                resid_acc <= 24'sd0;
            end

            if (eof && !sample_en) begin
                dbg_illum_bias <= resid_acc >>> 14;
                gain_err = $signed({8'd0, ALPHA_Q8}) - $signed({8'd0, gain_q8});
                gain_q8 <= gain_q8 + (gain_err >>> GAIN_BETA_SHIFT);
                dbg_gain_q8 <= gain_q8;
            end
        end
    end
endmodule
