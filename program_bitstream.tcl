set bit [lindex $argv 0]
if { $bit eq "" || ![file exists $bit] } { puts "Usage: vivado -mode tcl -source program_bitstream.tcl -tclargs <path_to.bit>"; exit 1 }
open_hw_manager
connect_hw_server
current_hw_target [lindex [get_hw_targets] 0]
open_hw_target
set dev [lindex [get_hw_devices] 0]
current_hw_device $dev
set_property PROGRAM.FILE $bit $dev
program_hw_devices $dev
refresh_hw_device $dev
close_hw_target
close_hw_manager
puts "Programmed: $bit"
exit
