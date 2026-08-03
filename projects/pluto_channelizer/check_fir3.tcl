create_project -in_memory -part xc7z010clg225-1
create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_probe
set core [get_ips fir_probe]
set_property CONFIG.Filter_Type Decimation $core
set_property CONFIG.Number_Channels 50 $core
set_property CONFIG.Decimation_Rate 50 $core
puts "set OK"
puts [report_property -all $core CONFIG.Number_Paths]
