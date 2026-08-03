create_project -in_memory -part xc7z010clg225-1
set ips [get_ipdefs]
foreach ip $ips {
    set nm [get_property NAME $ip]
    if {[string match "*fir*" $nm] || [string match "*fft*" $nm]} {
        puts "$ip :: [get_property DISPLAY_NAME $ip]"
    }
}
