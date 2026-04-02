module blob_bbox_tracker #(
    parameter integer IMG_W = 160,
    parameter integer IMG_H = 120,
    parameter integer MAX_BLOBS = 16,
    parameter integer MIN_AREA = 20
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       fg_valid,
    input  wire       fg_bit,
    input  wire [7:0] fg_x,
    input  wire [6:0] fg_y,
    input  wire       fg_sof,
    input  wire       fg_eof,
    output reg        emit_done,
    output reg        blob_valid,
    output reg [7:0]  blob_x,
    output reg [6:0]  blob_y,
    output reg [7:0]  blob_w,
    output reg [6:0]  blob_h,
    output reg [15:0] blob_area
);
    reg active [0:MAX_BLOBS-1];
    reg [7:0] bx0 [0:MAX_BLOBS-1];
    reg [7:0] bx1 [0:MAX_BLOBS-1];
    reg [6:0] by0 [0:MAX_BLOBS-1];
    reg [6:0] by1 [0:MAX_BLOBS-1];
    reg [15:0] barea [0:MAX_BLOBS-1];
    reg [6:0] last_y [0:MAX_BLOBS-1];
    reg [3:0] emit_idx;

    reg in_run;
    reg [7:0] run_x0;
    reg [7:0] run_x1;
    reg [6:0] run_y;

    integer i;
    integer hit;
    integer free_idx;
    integer candidate;
    integer run_len;

    task reset_blobs;
        integer k;
        begin
            for (k = 0; k < MAX_BLOBS; k = k + 1) begin
                active[k] = 1'b0;
                bx0[k] = 8'd0;
                bx1[k] = 8'd0;
                by0[k] = 7'd0;
                by1[k] = 7'd0;
                barea[k] = 16'd0;
                last_y[k] = 7'd0;
            end
            emit_idx = 4'd0;
            in_run = 1'b0;
        end
    endtask

    task process_run;
        begin
            run_len = run_x1 - run_x0 + 1;
            hit = -1;
            free_idx = -1;
            candidate = -1;

            for (i = 0; i < MAX_BLOBS; i = i + 1) begin
                if (!active[i] && free_idx < 0) begin
                    free_idx = i;
                end
                if (active[i] && last_y[i] + 1 >= run_y) begin
                    if (!(run_x1 < bx0[i] || run_x0 > bx1[i])) begin
                        if (hit < 0) begin
                            hit = i;
                        end
                    end
                end
            end

            if (hit >= 0) begin
                if (run_x0 < bx0[hit]) bx0[hit] = run_x0;
                if (run_x1 > bx1[hit]) bx1[hit] = run_x1;
                if (run_y < by0[hit]) by0[hit] = run_y;
                if (run_y > by1[hit]) by1[hit] = run_y;
                barea[hit] = barea[hit] + run_len[15:0];
                last_y[hit] = run_y;
            end else begin
                if (free_idx >= 0) begin
                    candidate = free_idx;
                end else begin
                    candidate = 0;
                    for (i = 1; i < MAX_BLOBS; i = i + 1) begin
                        if (barea[i] < barea[candidate]) candidate = i;
                    end
                end
                active[candidate] = 1'b1;
                bx0[candidate] = run_x0;
                bx1[candidate] = run_x1;
                by0[candidate] = run_y;
                by1[candidate] = run_y;
                barea[candidate] = run_len[15:0];
                last_y[candidate] = run_y;
            end
        end
    endtask

    always @(posedge clk) begin
        if (rst) begin
            emit_done <= 1'b0;
            blob_valid <= 1'b0;
            blob_x <= 8'd0;
            blob_y <= 7'd0;
            blob_w <= 8'd0;
            blob_h <= 7'd0;
            blob_area <= 16'd0;
            reset_blobs();
        end else begin
            emit_done <= 1'b0;
            blob_valid <= 1'b0;

            if (fg_sof) begin
                reset_blobs();
            end

            if (fg_valid) begin
                if (fg_bit) begin
                    if (!in_run) begin
                        in_run <= 1'b1;
                        run_x0 <= fg_x;
                        run_x1 <= fg_x;
                        run_y <= fg_y;
                    end else if (fg_y == run_y && fg_x == run_x1 + 1) begin
                        run_x1 <= fg_x;
                    end else begin
                        process_run();
                        in_run <= 1'b1;
                        run_x0 <= fg_x;
                        run_x1 <= fg_x;
                        run_y <= fg_y;
                    end
                end else if (in_run) begin
                    process_run();
                    in_run <= 1'b0;
                end
            end

            if (fg_eof) begin
                if (in_run) begin
                    process_run();
                    in_run <= 1'b0;
                end
                emit_idx <= 4'd0;
            end

            if (!fg_valid && emit_idx < MAX_BLOBS) begin
                if (active[emit_idx] && barea[emit_idx] >= MIN_AREA) begin
                    blob_valid <= 1'b1;
                    blob_x <= bx0[emit_idx];
                    blob_y <= by0[emit_idx];
                    blob_w <= bx1[emit_idx] - bx0[emit_idx] + 1'b1;
                    blob_h <= by1[emit_idx] - by0[emit_idx] + 1'b1;
                    blob_area <= barea[emit_idx];
                end
                if (emit_idx == MAX_BLOBS-1) emit_done <= 1'b1;
                emit_idx <= emit_idx + 1'b1;
            end
        end
    end
endmodule
