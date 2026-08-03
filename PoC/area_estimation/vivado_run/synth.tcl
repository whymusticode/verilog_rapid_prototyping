set_part xczu7ev-ffvc1156-2-e
read_verilog -sv kernel.h.sv
read_verilog -sv kernel.sv
synth_design -top kernel_top -part xczu7ev-ffvc1156-2-e
report_utilization -file util_synth.rpt
