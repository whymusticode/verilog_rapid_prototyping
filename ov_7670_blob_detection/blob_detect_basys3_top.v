module blob_detect_basys3_top #(
    parameter integer CLK_HZ = 25_000_000,
    parameter integer BAUD = 115200
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  pix_gray,
    input  wire        pix_valid,
    input  wire        sof,
    input  wire        eof,
    input  wire [10:0] x,
    input  wire [10:0] y,
    output wire        uart_tx_o,
    output wire [7:0]  dbg_gain_q8,
    output wire signed [8:0] dbg_illum_bias
);
    wire fg_valid;
    wire fg_bit;
    wire [7:0] fg_x;
    wire [6:0] fg_y;
    wire fg_sof;
    wire fg_eof;

    wire blob_valid;
    wire [7:0] blob_x;
    wire [6:0] blob_y;
    wire [7:0] blob_w;
    wire [6:0] blob_h;
    wire [15:0] blob_area;
    wire emit_done;

    wire [7:0] tx_data;
    wire tx_valid;
    wire tx_ready;

    blob_bg_model_qvga u_bg (
        .clk(clk),
        .rst(rst),
        .pix_in(pix_gray),
        .pix_valid(pix_valid),
        .sof(sof),
        .eof(eof),
        .x_in(x),
        .y_in(y),
        .fg_valid(fg_valid),
        .fg_bit(fg_bit),
        .fg_x(fg_x),
        .fg_y(fg_y),
        .fg_sof(fg_sof),
        .fg_eof(fg_eof),
        .dbg_gain_q8(dbg_gain_q8),
        .dbg_illum_bias(dbg_illum_bias)
    );

    blob_bbox_tracker u_bbox (
        .clk(clk),
        .rst(rst),
        .fg_valid(fg_valid),
        .fg_bit(fg_bit),
        .fg_x(fg_x),
        .fg_y(fg_y),
        .fg_sof(fg_sof),
        .fg_eof(fg_eof),
        .emit_done(emit_done),
        .blob_valid(blob_valid),
        .blob_x(blob_x),
        .blob_y(blob_y),
        .blob_w(blob_w),
        .blob_h(blob_h),
        .blob_area(blob_area)
    );

    blob_uart_packetizer u_pkt (
        .clk(clk),
        .rst(rst),
        .frame_start(fg_sof),
        .blob_valid(blob_valid),
        .blob_x(blob_x),
        .blob_y(blob_y),
        .blob_w(blob_w),
        .blob_h(blob_h),
        .blob_area(blob_area),
        .emit_done(emit_done),
        .tx_data(tx_data),
        .tx_valid(tx_valid),
        .tx_ready(tx_ready)
    );

    uart_tx #(
        .CLK_HZ(CLK_HZ),
        .BAUD(BAUD)
    ) u_uart (
        .clk(clk),
        .rst(rst),
        .tx_data(tx_data),
        .tx_valid(tx_valid),
        .tx_ready(tx_ready),
        .tx(uart_tx_o)
    );
endmodule
