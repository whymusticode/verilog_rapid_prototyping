create_project -in_memory -part xc7z010clg225-1
create_ip -vlnv xilinx.com:ip:xfft:9.1 -module_name fft_probe
set core [get_ips fft_probe]
puts "=== xfft CONFIG properties ==="
foreach p [list_property $core] {
    if {[string match "CONFIG.*" $p]} {
        puts "$p = [get_property $p $core]"
    }
}
