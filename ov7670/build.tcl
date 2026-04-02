set proj_dir [file normalize [file dirname [info script]]]
set proj_name ov7670_cam
create_project $proj_name $proj_dir/$proj_name -part xc7a35tcpg236-1 -force

set rtl_files [glob $proj_dir/rtl/*.vhd]
foreach f $rtl_files { add_files -fileset sources_1 $f }
add_files -fileset constrs_1 $proj_dir/Basys3.xdc

set_property top top_level [current_fileset]
set_property file_type {VHDL} [get_files *.vhd]

update_compile_order -fileset sources_1

launch_runs synth_1 -jobs 4
wait_on_run synth_1
if { [get_property PROGRESS [get_runs synth_1]] != "100%" } { error "Synth failed" }

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if { [get_property PROGRESS [get_runs impl_1]] != "100%" } { error "Impl failed" }

set rpt_dir $proj_dir/$proj_name/${proj_name}.runs/impl_1
puts "Bitstream: $rpt_dir/top_level.bit"
puts "Resource %%: $rpt_dir/utilization.rpt (LUT/FF/DSP/BRAM)"
exit
