# Polyphase channelizer benchmark for ADALM-Pluto (xc7z010clg225-1):
# 20 MHz input, 50 channels x 400 kHz, critically sampled (M=50).
#
# FIR Compiler's single-path TDM channelizer mode (Number_Paths=1,
# Number_Channels=50) caps input sample rate at Clock_Freq * 1.649 / 50
# (empirically measured: 14.84 MHz @ 450MHz clock) -- not enough for
# 20 MHz. Using Number_Paths=10, Number_Channels=5 (10 parallel engines,
# each TDM'ing 5 channels) instead: cap becomes 10x higher
# (148.4 MHz @ 450MHz clock), comfortably covering 20 MHz.

set part xc7z010clg225-1

set fp [open "proto_coeffs.txt" r]
set coeffs [read $fp]
close $fp

create_project -in_memory -part $part

# ---- Stage 1: polyphase decimating FIR filterbank ----
# 10 parallel paths x 5 TDM channels/path = 50 total channels
create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name polyphase_fir
set fir [get_ips polyphase_fir]

set_property CONFIG.Filter_Type Decimation $fir
set_property CONFIG.Rate_Change_Type Integer $fir
set_property CONFIG.Decimation_Rate 50 $fir
set_property CONFIG.Number_Channels 5 $fir
set_property CONFIG.Number_Paths 10 $fir
set_property CONFIG.CoefficientSource Vector $fir
set_property CONFIG.CoefficientVector $coeffs $fir
set_property CONFIG.Coefficient_Width 16 $fir
set_property CONFIG.Data_Width 16 $fir
set_property CONFIG.Output_Rounding_Mode Convergent_Rounding_to_Even $fir
set_property CONFIG.Output_Width 24 $fir
set_property CONFIG.Clock_Frequency 450.0 $fir
set_property CONFIG.Sample_Frequency 20.0 $fir
set_property CONFIG.RateSpecification Frequency_Specification $fir

generate_target {instantiation_template} $fir
generate_target all [get_files polyphase_fir.xci]

puts "=== FIR IP generated ==="

synth_design -mode out_of_context -top polyphase_fir -part $part
write_checkpoint -force polyphase_fir_synth.dcp
report_utilization -file util_fir.rpt
create_clock -period [expr {1000.0/450.0}] -name clk [get_ports aclk]
report_timing_summary -file timing_fir.rpt -max_paths 5

puts "=== FIR synthesis complete ==="
