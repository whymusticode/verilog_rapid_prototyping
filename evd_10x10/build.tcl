set proj_dir [file normalize [file dirname [info script]]]
set proj_name evd_10x10
set_param general.maxThreads 1
create_project $proj_name $proj_dir/$proj_name -part xc7a35tcpg236-1 -force

add_files -fileset sources_1 $proj_dir/top.v
add_files -fileset sources_1 $proj_dir/rtl/uart_rx.v
add_files -fileset sources_1 $proj_dir/rtl/uart_tx.v
add_files -fileset sources_1 $proj_dir/rtl/complex_mul_3dsp.v
add_files -fileset sources_1 $proj_dir/rtl/cmatmul10x10_dsp.v
add_files -fileset sources_1 $proj_dir/rtl/pivot_pairs_10x10.v
add_files -fileset sources_1 $proj_dir/rtl/jacobi_sweep10x10.v
add_files -fileset sources_1 $proj_dir/rtl/jacobi_engine10x10.v
add_files -fileset constrs_1 $proj_dir/Basys3.xdc

set_property top top [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 1
wait_on_run synth_1
if { [get_property PROGRESS [get_runs synth_1]] != "100%" } { error "Synth failed" }
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if { [get_property PROGRESS [get_runs impl_1]] != "100%" } { error "Impl failed" }
report_utilization -file $proj_dir/utilization.rpt
puts "Bitstream: $proj_dir/$proj_name/$proj_name.runs/impl_1/top.bit"
