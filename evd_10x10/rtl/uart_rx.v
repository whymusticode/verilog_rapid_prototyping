`timescale 1ns/1ps
module uart_rx #(
  parameter integer CLKS_PER_BIT = 868
) (
  input  wire clk,
  input  wire rst,
  input  wire rx,
  output reg  [7:0] data_out,
  output reg  data_valid
);
  localparam [2:0] S_IDLE  = 3'd0;
  localparam [2:0] S_START = 3'd1;
  localparam [2:0] S_DATA  = 3'd2;
  localparam [2:0] S_STOP  = 3'd3;

  reg [2:0] state;
  reg [15:0] clk_count;
  reg [2:0] bit_idx;
  reg [7:0] data_reg;

  always @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE;
      clk_count <= 0;
      bit_idx <= 0;
      data_reg <= 0;
      data_out <= 0;
      data_valid <= 1'b0;
    end else begin
      data_valid <= 1'b0;
      case (state)
        S_IDLE: begin
          clk_count <= 0;
          bit_idx <= 0;
          if (rx == 1'b0) state <= S_START;
        end
        S_START: begin
          if (clk_count == (CLKS_PER_BIT-1)/2) begin
            if (rx == 1'b0) begin
              clk_count <= 0;
              state <= S_DATA;
            end else begin
              state <= S_IDLE;
            end
          end else begin
            clk_count <= clk_count + 1'b1;
          end
        end
        S_DATA: begin
          if (clk_count < CLKS_PER_BIT-1) begin
            clk_count <= clk_count + 1'b1;
          end else begin
            clk_count <= 0;
            data_reg[bit_idx] <= rx;
            if (bit_idx == 3'd7) begin
              bit_idx <= 0;
              state <= S_STOP;
            end else begin
              bit_idx <= bit_idx + 1'b1;
            end
          end
        end
        S_STOP: begin
          if (clk_count < CLKS_PER_BIT-1) begin
            clk_count <= clk_count + 1'b1;
          end else begin
            data_out <= data_reg;
            data_valid <= 1'b1;
            clk_count <= 0;
            state <= S_IDLE;
          end
        end
        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
