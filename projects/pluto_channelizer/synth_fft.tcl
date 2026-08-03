# FFT stage for the polyphase channelizer: 64-point (next power-of-2 above
# 50 channels -- xfft requires power-of-2 transform length; 14 output bins
# unused/discarded), Pipelined Streaming I/O architecture for continuous
# real-time throughput matching the channelizer's always-on data stream.

set part xc7z010clg225-1
create_project -in_memory -part $part

create_ip -vlnv xilinx.com:ip:xfft:9.1 -module_name chan_fft
set fft [get_ips chan_fft]

set_property CONFIG.transform_length 64 $fft
set_property CONFIG.implementation_options pipelined_streaming_io $fft
set_property CONFIG.input_width 24 $fft
set_property CONFIG.phase_factor_width 24 $fft
set_property CONFIG.target_clock_frequency 331 $fft
set_property CONFIG.target_data_throughput 20 $fft
set_property CONFIG.data_format fixed_point $fft
set_property CONFIG.scaling_options scaled $fft
set_property CONFIG.rounding_modes convergent_rounding $fft

generate_target {instantiation_template} $fft
generate_target all [get_files chan_fft.xci]

puts "=== FFT IP generated ==="

synth_design -mode out_of_context -top chan_fft -part $part
write_checkpoint -force chan_fft_synth.dcp
report_utilization -file util_fft.rpt
report_timing_summary -file timing_fft.rpt -max_paths 5

puts "=== FFT synthesis complete ==="
