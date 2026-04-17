`timescale 1ns/1ps
module top (
  input  wire clk,
  input  wire btnC,
  input  wire RsRx,
  output wire RsTx,
  output wire [15:0] led
);
  localparam integer N = 10;
  localparam integer W = 23;
  localparam integer RX_BYTES = 604; // SOF + max_iter(2) + matrix(600) + crc
  localparam integer TX_BYTES = 65;  // SOF + status + iter(2) + diag(60) + crc

  wire rst = ~btnC;

  wire [7:0] rx_byte;
  wire rx_valid;
  reg [7:0] tx_byte;
  reg tx_send;
  wire tx_busy;
  wire tx_done;

  reg [N*N*24-1:0] a_re24_flat;
  reg [N*N*24-1:0] a_im24_flat;
  reg [9:0] rx_count;
  reg [7:0] rx_crc;
  reg [7:0] tx_crc_run;
  reg [7:0] status_code;
  reg [15:0] max_iter_reg;

  reg [7:0] io_state;
  localparam [7:0] IO_WAIT_SOF = 0;
  localparam [7:0] IO_RECV = 1;
  localparam [7:0] IO_PREP = 2;
  localparam [7:0] IO_SEND = 3;

  reg [7:0] tx_idx;
  reg [7:0] tx_data_sel;
  integer idx;
  integer bidx;
  integer elem;
  integer ofs;
  integer di;
  integer bo;
  reg signed [W-1:0] lane_i;
  reg signed [W-1:0] lane_q;
  reg [23:0] raw_i;
  reg [23:0] raw_q;

  reg engine_start;
  wire engine_done;
  wire engine_busy;
  wire [15:0] iter_count;
  reg signed [N*N*W-1:0] a_re_flat;
  reg signed [N*N*W-1:0] a_im_flat;
  wire signed [N*N*W-1:0] a_re_out;
  wire signed [N*N*W-1:0] a_im_out;
  wire signed [N*N*W-1:0] v_re_out;
  wire signed [N*N*W-1:0] v_im_out;

  always @* begin
    tx_data_sel = 8'h00;
    if (tx_idx == 8'd0) tx_data_sel = 8'h5A;
    else if (tx_idx == 8'd1) tx_data_sel = status_code;
    else if (tx_idx == 8'd2) tx_data_sel = iter_count[7:0];
    else if (tx_idx == 8'd3) tx_data_sel = iter_count[15:8];
    else if (tx_idx < TX_BYTES-1) begin
      di = (tx_idx - 8'd4) / 8'd6;
      bo = (tx_idx - 8'd4) % 8'd6;
      lane_i = a_re_out[(di*N+di)*W +: W];
      lane_q = a_im_out[(di*N+di)*W +: W];
      raw_i = {lane_i[W-1], lane_i};
      raw_q = {lane_q[W-1], lane_q};
      case (bo)
        0: tx_data_sel = raw_i[7:0];
        1: tx_data_sel = raw_i[15:8];
        2: tx_data_sel = raw_i[23:16];
        3: tx_data_sel = raw_q[7:0];
        4: tx_data_sel = raw_q[15:8];
        default: tx_data_sel = raw_q[23:16];
      endcase
    end else begin
      tx_data_sel = tx_crc_run;
    end
  end

  uart_rx #(.CLKS_PER_BIT(868)) u_rx (
    .clk(clk),
    .rst(rst),
    .rx(RsRx),
    .data_out(rx_byte),
    .data_valid(rx_valid)
  );

  uart_tx #(.CLKS_PER_BIT(868)) u_tx (
    .clk(clk),
    .rst(rst),
    .data_in(tx_byte),
    .send(tx_send),
    .tx(RsTx),
    .busy(tx_busy),
    .done(tx_done)
  );

  jacobi_engine10x10 #(.N(N), .W(W)) u_engine (
    .clk(clk),
    .rst(rst),
    .start(engine_start),
    .max_iter(max_iter_reg),
    .a_re_in(a_re_flat),
    .a_im_in(a_im_flat),
    .a_re_out(a_re_out),
    .a_im_out(a_im_out),
    .v_re_out(v_re_out),
    .v_im_out(v_im_out),
    .iter_count(iter_count),
    .busy(engine_busy),
    .done(engine_done)
  );

  always @(posedge clk) begin
    if (rst) begin
      io_state <= IO_WAIT_SOF;
      rx_count <= 0;
      rx_crc <= 0;
      tx_crc_run <= 0;
      tx_idx <= 0;
      tx_send <= 1'b0;
      tx_byte <= 8'h00;
      status_code <= 8'h00;
      max_iter_reg <= 16'd512;
      engine_start <= 1'b0;
      a_re_flat <= 0;
      a_im_flat <= 0;
      a_re24_flat <= 0;
      a_im24_flat <= 0;
    end else begin
      tx_send <= 1'b0;
      engine_start <= 1'b0;

      case (io_state)
        IO_WAIT_SOF: begin
          if (rx_valid && rx_byte == 8'hA5) begin
            rx_crc <= rx_byte;
            rx_count <= 10'd1;
            io_state <= IO_RECV;
          end
        end

        IO_RECV: begin
          if (rx_valid) begin
            if (rx_count < RX_BYTES-1) rx_crc <= rx_crc ^ rx_byte;
            if (rx_count == 10'd1) max_iter_reg[7:0] <= rx_byte;
            else if (rx_count == 10'd2) max_iter_reg[15:8] <= rx_byte;
            else if (rx_count >= 10'd3 && rx_count <= 10'd602) begin
              bidx = rx_count - 10'd3;
              elem = bidx / 6;
              ofs = bidx % 6;
              case (ofs)
                0: a_re24_flat[elem*24 +: 8] <= rx_byte;
                1: a_re24_flat[elem*24+8 +: 8] <= rx_byte;
                2: a_re24_flat[elem*24+16 +: 8] <= rx_byte;
                3: a_im24_flat[elem*24 +: 8] <= rx_byte;
                4: a_im24_flat[elem*24+8 +: 8] <= rx_byte;
                default: a_im24_flat[elem*24+16 +: 8] <= rx_byte;
              endcase
            end
            if (rx_count == RX_BYTES-1) begin
              if (rx_crc == rx_byte) begin
                for (idx = 0; idx < N*N; idx = idx + 1) begin
                  a_re_flat[idx*W +: W] <= a_re24_flat[idx*24 +: W];
                  a_im_flat[idx*W +: W] <= a_im24_flat[idx*24 +: W];
                end
                status_code <= 8'h00;
                engine_start <= 1'b1;
                io_state <= IO_PREP;
              end else begin
                status_code <= 8'h01;
                io_state <= IO_PREP;
              end
            end else begin
              rx_count <= rx_count + 1'b1;
            end
          end
        end

        IO_PREP: begin
          if (status_code != 8'h00 || engine_done) begin
            tx_crc_run <= 8'h00;
            tx_idx <= 0;
            io_state <= IO_SEND;
          end
        end

        IO_SEND: begin
          if (!tx_busy && !tx_send) begin
            tx_byte <= tx_data_sel;
            tx_send <= 1'b1;
          end
          if (tx_done) begin
            if (tx_idx < TX_BYTES-1) tx_crc_run <= tx_crc_run ^ tx_byte;
            if (tx_idx == TX_BYTES-1) begin
              io_state <= IO_WAIT_SOF;
              rx_count <= 0;
              rx_crc <= 0;
            end else begin
              tx_idx <= tx_idx + 1'b1;
            end
          end
        end

        default: io_state <= IO_WAIT_SOF;
      endcase
    end
  end

  assign led[0] = engine_busy;
  assign led[1] = engine_done;
  assign led[2] = (status_code != 0);
  assign led[15:3] = 13'd0;
endmodule
