set proj_dir [file normalize [file dirname [info script]]]
set bit $proj_dir/evd_10x10/evd_10x10.runs/impl_1/top.bit
if { ![file exists $bit] } { puts "Run build.tcl first"; exit 1 }

open_hw_manager
connect_hw_server
set servers [get_hw_servers]
if { [llength $servers] == 0 } { puts "No hw_server"; exit 1 }
set targets [get_hw_targets -of_objects [lindex $servers 0]]
if { [llength $targets] == 0 } { puts "No target; run usb attach first"; exit 1 }

current_hw_target [lindex $targets 0]
open_hw_target
set devs [get_hw_devices]
if { [llength $devs] == 0 } { puts "No hw devices"; exit 1 }
current_hw_device [lindex $devs 0]
set_property PROGRAM.FILE $bit [lindex $devs 0]
program_hw_devices [lindex $devs 0]
refresh_hw_device [lindex $devs 0]
close_hw_target
close_hw_manager
puts "Program complete"
exit
