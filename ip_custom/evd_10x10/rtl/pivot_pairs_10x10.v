`timescale 1ns/1ps
module pivot_pairs_10x10 (
  input  wire [5:0] pair_idx,
  output reg  [3:0] p_idx,
  output reg  [3:0] q_idx
);
  always @* begin
    p_idx = 0;
    q_idx = 1;
    case (pair_idx)
      6'd0:  begin p_idx = 0; q_idx = 1; end
      6'd1:  begin p_idx = 0; q_idx = 2; end
      6'd2:  begin p_idx = 0; q_idx = 3; end
      6'd3:  begin p_idx = 0; q_idx = 4; end
      6'd4:  begin p_idx = 0; q_idx = 5; end
      6'd5:  begin p_idx = 0; q_idx = 6; end
      6'd6:  begin p_idx = 0; q_idx = 7; end
      6'd7:  begin p_idx = 0; q_idx = 8; end
      6'd8:  begin p_idx = 0; q_idx = 9; end
      6'd9:  begin p_idx = 1; q_idx = 2; end
      6'd10: begin p_idx = 1; q_idx = 3; end
      6'd11: begin p_idx = 1; q_idx = 4; end
      6'd12: begin p_idx = 1; q_idx = 5; end
      6'd13: begin p_idx = 1; q_idx = 6; end
      6'd14: begin p_idx = 1; q_idx = 7; end
      6'd15: begin p_idx = 1; q_idx = 8; end
      6'd16: begin p_idx = 1; q_idx = 9; end
      6'd17: begin p_idx = 2; q_idx = 3; end
      6'd18: begin p_idx = 2; q_idx = 4; end
      6'd19: begin p_idx = 2; q_idx = 5; end
      6'd20: begin p_idx = 2; q_idx = 6; end
      6'd21: begin p_idx = 2; q_idx = 7; end
      6'd22: begin p_idx = 2; q_idx = 8; end
      6'd23: begin p_idx = 2; q_idx = 9; end
      6'd24: begin p_idx = 3; q_idx = 4; end
      6'd25: begin p_idx = 3; q_idx = 5; end
      6'd26: begin p_idx = 3; q_idx = 6; end
      6'd27: begin p_idx = 3; q_idx = 7; end
      6'd28: begin p_idx = 3; q_idx = 8; end
      6'd29: begin p_idx = 3; q_idx = 9; end
      6'd30: begin p_idx = 4; q_idx = 5; end
      6'd31: begin p_idx = 4; q_idx = 6; end
      6'd32: begin p_idx = 4; q_idx = 7; end
      6'd33: begin p_idx = 4; q_idx = 8; end
      6'd34: begin p_idx = 4; q_idx = 9; end
      6'd35: begin p_idx = 5; q_idx = 6; end
      6'd36: begin p_idx = 5; q_idx = 7; end
      6'd37: begin p_idx = 5; q_idx = 8; end
      6'd38: begin p_idx = 5; q_idx = 9; end
      6'd39: begin p_idx = 6; q_idx = 7; end
      6'd40: begin p_idx = 6; q_idx = 8; end
      6'd41: begin p_idx = 6; q_idx = 9; end
      6'd42: begin p_idx = 7; q_idx = 8; end
      6'd43: begin p_idx = 7; q_idx = 9; end
      6'd44: begin p_idx = 8; q_idx = 9; end
      default: begin p_idx = 0; q_idx = 1; end
    endcase
  end
endmodule
