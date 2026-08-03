create_project -in_memory -part xc7z010clg225-1
set ips [get_ipdefs]
foreach ip $ips {
    set nm [get_property NAME $ip]
    if {[string match "*chan*" $nm] || [string match "*ddc*" $nm] || [string match "*poly*" $nm] || [string match "*filterbank*" $nm] || [string match "*fbmc*" $nm]} {
        puts "$ip :: [get_property DISPLAY_NAME $ip]"
    }
}
