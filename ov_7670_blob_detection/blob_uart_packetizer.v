module blob_uart_packetizer #(
    parameter integer MAX_BLOBS = 16
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       frame_start,
    input  wire       blob_valid,
    input  wire [7:0] blob_x,
    input  wire [6:0] blob_y,
    input  wire [7:0] blob_w,
    input  wire [6:0] blob_h,
    input  wire [15:0] blob_area,
    input  wire       emit_done,
    output reg [7:0]  tx_data,
    output reg        tx_valid,
    input  wire       tx_ready
);
    reg [15:0] frame_id;
    reg [4:0] blob_count;

    reg [7:0] bx [0:MAX_BLOBS-1];
    reg [6:0] by [0:MAX_BLOBS-1];
    reg [7:0] bw [0:MAX_BLOBS-1];
    reg [6:0] bh [0:MAX_BLOBS-1];
    reg [15:0] ba [0:MAX_BLOBS-1];

    reg [1:0] state;
    reg [4:0] out_blob_idx;
    reg [2:0] out_field_idx;
    localparam S_IDLE = 2'd0;
    localparam S_HDR  = 2'd1;
    localparam S_BLOB = 2'd2;

    reg [2:0] hdr_idx;

    integer i;
    always @(posedge clk) begin
        if (rst) begin
            frame_id <= 16'd0;
            blob_count <= 5'd0;
            tx_data <= 8'd0;
            tx_valid <= 1'b0;
            state <= S_IDLE;
            out_blob_idx <= 5'd0;
            out_field_idx <= 3'd0;
            hdr_idx <= 3'd0;
            for (i = 0; i < MAX_BLOBS; i = i + 1) begin
                bx[i] <= 8'd0;
                by[i] <= 7'd0;
                bw[i] <= 8'd0;
                bh[i] <= 7'd0;
                ba[i] <= 16'd0;
            end
        end else begin
            tx_valid <= 1'b0;

            if (frame_start) begin
                frame_id <= frame_id + 1'b1;
                blob_count <= 5'd0;
            end

            if (blob_valid && blob_count < MAX_BLOBS) begin
                bx[blob_count] <= blob_x;
                by[blob_count] <= blob_y;
                bw[blob_count] <= blob_w;
                bh[blob_count] <= blob_h;
                ba[blob_count] <= blob_area;
                blob_count <= blob_count + 1'b1;
            end

            case (state)
                S_IDLE: begin
                    if (emit_done) begin
                        state <= S_HDR;
                        hdr_idx <= 3'd0;
                    end
                end

                S_HDR: begin
                    if (tx_ready) begin
                        tx_valid <= 1'b1;
                        case (hdr_idx)
                            3'd0: tx_data <= 8'hAA;          // SOF
                            3'd1: tx_data <= 8'h01;          // packet type
                            3'd2: tx_data <= frame_id[15:8];
                            3'd3: tx_data <= frame_id[7:0];
                            3'd4: tx_data <= {3'b000, blob_count};
                            default: tx_data <= 8'h00;
                        endcase
                        if (hdr_idx == 3'd4) begin
                            state <= S_BLOB;
                            out_blob_idx <= 5'd0;
                            out_field_idx <= 3'd0;
                        end else begin
                            hdr_idx <= hdr_idx + 1'b1;
                        end
                    end
                end

                S_BLOB: begin
                    if (out_blob_idx < blob_count) begin
                        if (tx_ready) begin
                            tx_valid <= 1'b1;
                            case (out_field_idx)
                                3'd0: tx_data <= bx[out_blob_idx];
                                3'd1: tx_data <= {1'b0, by[out_blob_idx]};
                                3'd2: tx_data <= bw[out_blob_idx];
                                3'd3: tx_data <= {1'b0, bh[out_blob_idx]};
                                3'd4: tx_data <= ba[out_blob_idx][15:8];
                                3'd5: tx_data <= ba[out_blob_idx][7:0];
                                3'd6: tx_data <= 8'd0; // class placeholder
                                3'd7: tx_data <= 8'd0; // flags placeholder
                                default: tx_data <= 8'd0;
                            endcase

                            if (out_field_idx == 3'd7) begin
                                out_field_idx <= 3'd0;
                                out_blob_idx <= out_blob_idx + 1'b1;
                            end else begin
                                out_field_idx <= out_field_idx + 1'b1;
                            end
                        end
                    end else if (tx_ready) begin
                        tx_valid <= 1'b1;
                        tx_data <= 8'h55; // EOF marker
                        state <= S_IDLE;
                    end
                end
            endcase
        end
    end
endmodule
