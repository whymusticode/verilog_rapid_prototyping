module uart_tx #(
    parameter integer CLK_HZ = 25_000_000,
    parameter integer BAUD = 115200
) (
    input  wire      clk,
    input  wire      rst,
    input  wire [7:0] tx_data,
    input  wire      tx_valid,
    output reg       tx_ready,
    output reg       tx
);
    localparam integer DIV = CLK_HZ / BAUD;

    reg [15:0] div_cnt;
    reg [3:0] bit_idx;
    reg [9:0] shreg;
    reg busy;

    always @(posedge clk) begin
        if (rst) begin
            tx <= 1'b1;
            tx_ready <= 1'b1;
            div_cnt <= 16'd0;
            bit_idx <= 4'd0;
            shreg <= 10'h3FF;
            busy <= 1'b0;
        end else begin
            if (!busy) begin
                tx <= 1'b1;
                tx_ready <= 1'b1;
                if (tx_valid) begin
                    busy <= 1'b1;
                    tx_ready <= 1'b0;
                    shreg <= {1'b1, tx_data, 1'b0}; // stop,data,start
                    bit_idx <= 4'd0;
                    div_cnt <= 16'd0;
                end
            end else begin
                if (div_cnt == DIV - 1) begin
                    div_cnt <= 16'd0;
                    tx <= shreg[0];
                    shreg <= {1'b1, shreg[9:1]};
                    bit_idx <= bit_idx + 1'b1;
                    if (bit_idx == 4'd9) begin
                        busy <= 1'b0;
                    end
                end else begin
                    div_cnt <= div_cnt + 1'b1;
                end
            end
        end
    end
endmodule
