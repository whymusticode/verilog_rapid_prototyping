# Composable wrapper: add RTL libs here; top.v wires them. Run from basys: build cordic_demo
set proj_dir [file normalize [file dirname [info script]]]
set basys_root [file normalize [file join $proj_dir ..]]
set proj_name cordic_demo
create_project $proj_name $proj_dir/$proj_name -part xc7a35tcpg236-1 -force
# RTL blocks (paths relative to basys_root). Add e.g. $basys_root/sqrt/rtl/sqrt.v for sin->sqrt chain.
set rtl_libs {
  cordic/rtl/cordic.v
}
foreach lib $rtl_libs { add_files -fileset sources_1 $basys_root/$lib }
add_files -fileset sources_1 $proj_dir/top.v
add_files -fileset constrs_1 $proj_dir/Basys3.xdc
set_property top top [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if { [get_property PROGRESS [get_runs synth_1]] != "100%" } { error "Synth failed" }
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if { [get_property PROGRESS [get_runs impl_1]] != "100%" } { error "Impl failed" }
set rpt_dir $proj_dir/$proj_name/$proj_name.runs/impl_1
open_run impl_1
report_utilization -file $rpt_dir/utilization.rpt -hierarchical
puts "Bitstream: $rpt_dir/top.bit"
puts "Resource %%: $rpt_dir/utilization.rpt (LUT/FF/DSP/BRAM)"
exit
