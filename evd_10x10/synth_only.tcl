set proj_dir [file normalize [file dirname [info script]]]
read_verilog $proj_dir/top.v
read_verilog $proj_dir/rtl/uart_rx.v
read_verilog $proj_dir/rtl/uart_tx.v
read_verilog $proj_dir/rtl/complex_mul_3dsp.v
read_verilog $proj_dir/rtl/cmatmul10x10_dsp.v
read_verilog $proj_dir/rtl/pivot_pairs_10x10.v
read_verilog $proj_dir/rtl/jacobi_sweep10x10.v
read_verilog $proj_dir/rtl/jacobi_engine10x10.v
read_xdc $proj_dir/Basys3.xdc
synth_design -top top -part xc7a35tcpg236-1 -flatten_hierarchy none
report_utilization -file $proj_dir/util_synth_only.rpt
exit
