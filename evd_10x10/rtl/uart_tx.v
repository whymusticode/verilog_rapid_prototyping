`timescale 1ns/1ps
module uart_tx #(
  parameter integer CLKS_PER_BIT = 868
) (
  input  wire clk,
  input  wire rst,
  input  wire [7:0] data_in,
  input  wire send,
  output reg  tx,
  output reg  busy,
  output reg  done
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
      tx <= 1'b1;
      busy <= 1'b0;
      done <= 1'b0;
    end else begin
      done <= 1'b0;
      case (state)
        S_IDLE: begin
          tx <= 1'b1;
          busy <= 1'b0;
          clk_count <= 0;
          bit_idx <= 0;
          if (send) begin
            data_reg <= data_in;
            busy <= 1'b1;
            state <= S_START;
          end
        end
        S_START: begin
          tx <= 1'b0;
          if (clk_count < CLKS_PER_BIT-1) begin
            clk_count <= clk_count + 1'b1;
          end else begin
            clk_count <= 0;
            state <= S_DATA;
          end
        end
        S_DATA: begin
          tx <= data_reg[bit_idx];
          if (clk_count < CLKS_PER_BIT-1) begin
            clk_count <= clk_count + 1'b1;
          end else begin
            clk_count <= 0;
            if (bit_idx == 3'd7) begin
              bit_idx <= 0;
              state <= S_STOP;
            end else begin
              bit_idx <= bit_idx + 1'b1;
            end
          end
        end
        S_STOP: begin
          tx <= 1'b1;
          if (clk_count < CLKS_PER_BIT-1) begin
            clk_count <= clk_count + 1'b1;
          end else begin
            state <= S_IDLE;
            clk_count <= 0;
            done <= 1'b1;
          end
        end
        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
