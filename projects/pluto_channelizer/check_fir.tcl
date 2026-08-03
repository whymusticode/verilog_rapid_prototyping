create_project -in_memory -part xc7z010clg225-1
create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_probe
set core [get_ips fir_probe]
puts "=== FIR Compiler CONFIG properties ==="
foreach p [list_property $core] {
    if {[string match "CONFIG.*" $p]} {
        puts "$p = [get_property $p $core]"
    }
}
