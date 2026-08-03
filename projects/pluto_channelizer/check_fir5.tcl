create_project -in_memory -part xc7z010clg225-1
create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_probe
set core [get_ips fir_probe]
set_property CONFIG.Filter_Type Decimation $core
set_property CONFIG.Rate_Change_Type Integer $core
set_property CONFIG.Decimation_Rate 50 $core
set_property CONFIG.Number_Channels 50 $core
set_property CONFIG.Number_Paths 1 $core
set_property CONFIG.Clock_Frequency 450.0 $core
if {[catch {set_property CONFIG.Sample_Frequency 20.0 $core} err]} {
    puts "ERROR: $err"
} else {
    puts "SUCCESS: sample freq set to 20.0 at clock 450"
}
