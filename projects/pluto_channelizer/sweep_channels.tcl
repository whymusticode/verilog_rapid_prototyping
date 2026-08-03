proc try_channels {nchan clkfreq} {
    create_project -in_memory -force -part xc7z010clg225-1
    create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_sweep
    set core [get_ips fir_sweep]
    set_property CONFIG.Filter_Type Decimation $core
    set_property CONFIG.Rate_Change_Type Integer $core
    set_property CONFIG.Decimation_Rate $nchan $core
    set_property CONFIG.Number_Channels $nchan $core
    set_property CONFIG.Number_Paths 1 $core
    set_property CONFIG.Clock_Frequency $clkfreq $core

    if {[catch {set_property CONFIG.Sample_Frequency 1000.0 $core} err]} {
        if {[regexp {range \(([0-9.e-]+),([0-9.e-]+)\)} $err -> lo hi]} {
            puts "RESULT nchan=$nchan clk=$clkfreq: max_sample_freq_MHz=$hi"
        } else {
            puts "RESULT nchan=$nchan clk=$clkfreq: ERROR (unparsed): $err"
        }
    }
}

try_channels 50 300.0
try_channels 50 450.0
try_channels 25 450.0
try_channels 10 450.0
try_channels 4 450.0
try_channels 2 450.0
try_channels 1 450.0
