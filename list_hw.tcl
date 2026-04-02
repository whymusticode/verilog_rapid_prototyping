# List hardware; open target so JTAG is probed and FPGA appears
open_hw_manager
connect_hw_server
puts "=== Hardware servers ==="
puts [get_hw_servers]
foreach server [get_hw_servers] {
    if { [catch { set targets [get_hw_targets -of_objects $server] } err] } {
        puts "Server $server: (no targets)"
    } else {
        puts "=== Targets ==="
        foreach t $targets { puts "  $t" }
        # Open first target to probe JTAG chain and discover FPGA
        if { [llength $targets] > 0 } {
            set t [lindex $targets 0]
            puts "=== Opening target (probe JTAG): $t ==="
            current_hw_target $t
            open_hw_target
            puts "=== Devices (FPGA) on chain ==="
            puts [get_hw_devices]
            close_hw_target
        }
    }
}
close_hw_manager
exit
