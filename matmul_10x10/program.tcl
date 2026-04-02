# Program Basys3 with existing bitstream. Requires usbipd + attach.
# Usage: vivado -mode batch -source matmul_10x10/program.tcl
set proj_dir [file normalize [file dirname [info script]]]
set bit $proj_dir/matmul_10x10/matmul_10x10.runs/impl_1/top.bit
if { ![file exists $bit] } { puts "Run build.tcl first"; exit 1 }
open_hw_manager
connect_hw_server
set servers [get_hw_servers]
if { [llength $servers] == 0 } { puts "No hw_server"; exit 1 }
set targets [get_hw_targets -of_objects [lindex $servers 0]]
if { [llength $targets] == 0 } { puts "No target; start usbipd and attach Basys"; exit 1 }
current_hw_target [lindex $targets 0]
open_hw_target
set devs [get_hw_devices]
current_hw_device [lindex $devs 0]
set_property PROGRAM.FILE $bit [lindex $devs 0]
program_hw_devices [lindex $devs 0]
refresh_hw_device [lindex $devs 0]
close_hw_target
close_hw_manager
puts "Done. Press center button; LED0 = 1 (C[0][0])."
exit
