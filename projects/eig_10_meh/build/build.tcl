set_part xczu7ev-ffvc1156-2-e
set_param general.maxThreads 4
read_verilog rtl/eigenvalue_decomposition.v
read_verilog rtl/top.v
read_xdc constraints/timing.xdc
synth_design -top top -part xczu7ev-ffvc1156-2-e
report_utilization -file reports/util_synth.rpt
report_timing_summary -file reports/timing_synth.rpt
