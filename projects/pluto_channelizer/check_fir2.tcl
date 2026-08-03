create_project -in_memory -part xc7z010clg225-1
create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_probe
set core [get_ips fir_probe]
puts "Filter_Type options: [list_property_value -object $core CONFIG.Filter_Type]"
puts "Rate_Change_Type options: [list_property_value -object $core CONFIG.Rate_Change_Type]"
