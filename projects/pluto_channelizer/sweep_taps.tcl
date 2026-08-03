# Empirically sweep taps-per-phase (via CoefficientVector length) to see how
# Vivado's live Sample_Frequency cap moves, at fixed Number_Channels=50,
# Number_Paths=1, Clock_Frequency=450.
create_project -in_memory -part xc7z010clg225-1

proc try_taps {taps_per_phase} {
    set n_taps [expr {$taps_per_phase * 50}]
    set coeffs {}
    for {set i 0} {$i < $n_taps} {incr i} {
        lappend coeffs 100
    }
    set coeffs_str [join $coeffs ","]

    catch {delete_ip [get_ips -quiet fir_sweep]}
    create_ip -vlnv xilinx.com:ip:fir_compiler:7.2 -module_name fir_sweep
    set core [get_ips fir_sweep]
    set_property CONFIG.Filter_Type Decimation $core
    set_property CONFIG.Rate_Change_Type Integer $core
    set_property CONFIG.Decimation_Rate 50 $core
    set_property CONFIG.Number_Channels 50 $core
    set_property CONFIG.Number_Paths 1 $core
    set_property CONFIG.CoefficientSource Vector $core
    set_property CONFIG.CoefficientVector $coeffs_str $core
    set_property CONFIG.Clock_Frequency 450.0 $core

    if {[catch {set_property CONFIG.Sample_Frequency 20.0 $core} err]} {
        # parse the range out of the error message
        if {[regexp {range \(([0-9.e-]+),([0-9.e-]+)\)} $err -> lo hi]} {
            puts "taps_per_phase=$taps_per_phase (n_taps=$n_taps): max_sample_freq_MHz=$hi"
        } else {
            puts "taps_per_phase=$taps_per_phase: ERROR (unparsed): $err"
        }
    } else {
        puts "taps_per_phase=$taps_per_phase (n_taps=$n_taps): 20.0 MHz ACCEPTED"
    }
}

foreach t {1 2 3 4 6 8 12} {
    try_taps $t
}
