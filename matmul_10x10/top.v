// 10x10 matrix multiply C = A*B, 8-bit elements. Shows C[0][0] on LEDs.
// A,B = identity => C[0][0] = 1 (LED0 on). btnC = reset/start.
`timescale 1ns/1ps
module top (
  input  wire       clk,
  input  wire       btnC,
  output wire [15:0] led
);
  reg [7:0] A [0:99];
  reg [7:0] B [0:99];
  reg [15:0] C00;
  reg [3:0] k;
  reg [6:0] init_cnt;
  reg [1:0] state;
  reg [19:0] sum;

  localparam S_INIT = 0, S_COMPUTE = 1, S_DONE = 2;

  wire [7:0] a_ik = A[k];           // A[0][k]
  wire [7:0] b_k0 = B[k*10];        // B[k][0]
  wire [15:0] prod = a_ik * b_k0;

  always @(posedge clk) begin
    if (!btnC) begin  // Basys3 buttons active-low: pressed = 0
      state <= S_INIT;
      init_cnt <= 0;
      k <= 0;
      sum <= 0;
    end else
    case (state)
      S_INIT: begin
        A[init_cnt] <= (init_cnt == 0 || init_cnt == 11 || init_cnt == 22 || init_cnt == 33 || init_cnt == 44 ||
                        init_cnt == 55 || init_cnt == 66 || init_cnt == 77 || init_cnt == 88 || init_cnt == 99) ? 8'd1 : 8'd0;
        B[init_cnt] <= (init_cnt == 0 || init_cnt == 11 || init_cnt == 22 || init_cnt == 33 || init_cnt == 44 ||
                        init_cnt == 55 || init_cnt == 66 || init_cnt == 77 || init_cnt == 88 || init_cnt == 99) ? 8'd1 : 8'd0;
        if (init_cnt == 99) state <= S_COMPUTE;
        else init_cnt <= init_cnt + 1;
        k <= 0;
        sum <= 0;
      end
      S_COMPUTE: begin
        if (k < 10) begin
          sum <= sum + prod;
          k <= k + 1;
        end else begin
          C00 <= sum[15:0];
          state <= S_DONE;
        end
      end
      S_DONE: ;
      default: ;
    endcase
  end

  assign led = (state == S_DONE) ? C00 : 16'd0;
endmodule
