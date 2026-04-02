`timescale 1ns/1ps
module tb_blob_bg_model;
    localparam integer OUT_W = 160;
    localparam integer OUT_H = 120;
    localparam integer FRAMES = 30;
    localparam integer N_PIX = OUT_W * OUT_H * FRAMES;

    reg clk = 1'b0;
    reg rst = 1'b1;
    always #10 clk = ~clk; // 50 MHz

    reg [7:0] pix_in;
    reg pix_valid;
    reg sof;
    reg eof;
    reg [10:0] x_in;
    reg [10:0] y_in;

    wire fg_valid;
    wire fg_bit;
    wire [7:0] fg_x;
    wire [6:0] fg_y;
    wire fg_sof;
    wire fg_eof;
    wire [7:0] dbg_gain_q8;
    wire signed [8:0] dbg_illum_bias;

    blob_bg_model_qvga #(
        .IN_W(640),
        .IN_H(480),
        .DS_LOG2(2),
        .OUT_W(OUT_W),
        .OUT_H(OUT_H),
        .N_PIX(OUT_W*OUT_H),
        .FG_THRESH(8'd18),
        .ALPHA_Q8(8'd10),
        .FG_LEAK_Q8(8'd1),
        .GAIN_BETA_SHIFT(4)
    ) u_dut (
        .clk(clk),
        .rst(rst),
        .pix_in(pix_in),
        .pix_valid(pix_valid),
        .sof(sof),
        .eof(eof),
        .x_in(x_in),
        .y_in(y_in),
        .fg_valid(fg_valid),
        .fg_bit(fg_bit),
        .fg_x(fg_x),
        .fg_y(fg_y),
        .fg_sof(fg_sof),
        .fg_eof(fg_eof),
        .dbg_gain_q8(dbg_gain_q8),
        .dbg_illum_bias(dbg_illum_bias)
    );

    reg [7:0] pix_mem [0:N_PIX-1];
    integer idx;
    integer f;
    integer x;
    integer y;

    integer fg_count;
    integer fg_count_latched;
    integer frame_idx;
    reg print_pending;

    always @(posedge clk) begin
        if (rst) begin
            fg_count <= 0;
            fg_count_latched <= 0;
            frame_idx <= 0;
            print_pending <= 1'b0;
        end else begin
            if (fg_valid) begin
                if (fg_sof) fg_count = 0;
                if (fg_bit) fg_count = fg_count + 1;
            end
            if (fg_valid && fg_eof) begin
                fg_count_latched <= fg_count;
                print_pending <= 1'b1;
            end else if (print_pending) begin
                $display("SIMDBG_V frame=%03d gain_q8=%03d illum=%0d fg=%05d bg0=%03d",
                         frame_idx, u_dut.gain_q8, u_dut.dbg_illum_bias, fg_count_latched, u_dut.bg_mem[0]);
                frame_idx <= frame_idx + 1;
                print_pending <= 1'b0;
            end
        end
    end

    initial begin
        $readmemh("sim_ds_pixels.mem", pix_mem);
        pix_in = 8'd0;
        pix_valid = 1'b0;
        sof = 1'b0;
        eof = 1'b0;
        x_in = 11'd0;
        y_in = 11'd0;

        repeat (4) @(posedge clk);
        rst = 1'b0;
        repeat (2) @(posedge clk);

        idx = 0;
        for (f = 0; f < FRAMES; f = f + 1) begin
            for (y = 0; y < OUT_H; y = y + 1) begin
                for (x = 0; x < OUT_W; x = x + 1) begin
                    @(posedge clk);
                    pix_valid <= 1'b1;
                    pix_in <= pix_mem[idx];
                    x_in <= x << 2;
                    y_in <= y << 2;
                    sof <= (x == 0 && y == 0);
                    eof <= (x == OUT_W-1 && y == OUT_H-1);
                    idx = idx + 1;
                end
            end
            @(posedge clk);
            pix_valid <= 1'b0;
            sof <= 1'b0;
            eof <= 1'b0;
        end

        repeat (20) @(posedge clk);
        $finish;
    end
endmodule
