proc try_config {npaths nchan clkfreq} {
    create_project -in_memory -force -part xc7z010clg225-1
    create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_sweep
    set core [get_ips fir_sweep]
    set_property CONFIG.Filter_Type Decimation $core
    set_property CONFIG.Rate_Change_Type Integer $core
    set_property CONFIG.Decimation_Rate [expr {$npaths * $nchan}] $core
    set_property CONFIG.Number_Channels $nchan $core
    set_property CONFIG.Number_Paths $npaths $core
    set_property CONFIG.Clock_Frequency $clkfreq $core

    if {[catch {set_property CONFIG.Sample_Frequency 1000.0 $core} err]} {
        if {[regexp {range \(([0-9.e-]+),([0-9.e-]+)\)} $err -> lo hi]} {
            puts "RESULT npaths=$npaths nchan=$nchan clk=$clkfreq: max_sample_freq_MHz=$hi"
        } else {
            puts "RESULT npaths=$npaths nchan=$nchan clk=$clkfreq: ERROR (unparsed): $err"
        }
    }
}

try_config 1 50 450.0
try_config 2 25 450.0
try_config 5 10 450.0
try_config 10 5 450.0
try_config 16 4 450.0
