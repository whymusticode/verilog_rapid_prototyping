// Bare-minimum DUT: counts up to N on start, asserts done for one cycle.
// Deliberately takes a known number of clock cycles so we can check the
// testbench's cycle count against a hand-computed expected value.
module dut #(
    parameter N = 5
) (
    input  wire clk,
    input  wire rst,
    input  wire start,
    output reg  busy,
    output reg  done
);
    reg [31:0] count;

    always @(posedge clk) begin
        if (rst) begin
            busy  <= 0;
            done  <= 0;
            count <= 0;
        end else begin
            done <= 0;
            if (start && !busy) begin
                busy  <= 1;
                count <= 0;
            end else if (busy) begin
                if (count == N - 1) begin
                    busy <= 0;
                    done <= 1;
                end else begin
                    count <= count + 1;
                end
            end
        end
    end
endmodule