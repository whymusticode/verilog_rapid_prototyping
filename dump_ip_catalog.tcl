set proj_dir [file normalize [file dirname [info script]]]
set tmp_proj "$proj_dir/_ipcatalog_proj"
set out_file "$proj_dir/ip_catalog.txt"

# Fresh disk-backed project (in_memory breaks create_ip with __prefix bug)
file delete -force $tmp_proj
create_project ipcat $tmp_proj -part xc7a35tcpg236-1 -force

set fd [open $out_file w]

set ips [get_ipdefs -filter {VLNV =~ "xilinx.com:ip:*"}]
set supported {}
foreach ip [lsort $ips] {
    set fams [string tolower [get_property SUPPORTED_FAMILIES $ip]]
    if {[string match "*artix7*" $fams]} { lappend supported $ip }
}

set total [llength $supported]
puts $fd "# Vivado IP Catalog"
puts $fd "# Generated: [clock format [clock seconds]]"
puts $fd "# Vivado: [version -short]"
puts $fd "# Part: xc7a35tcpg236-1 (Basys3 / Artix-7)"
puts $fd "# Total supported IPs: $total"
puts $fd "#"
puts $fd "# Format per IP:"
puts $fd "#   ### <name> | <vlnv> | <display_name>"
puts $fd "#   CAT: <taxonomy>"
puts $fd "#   DESC: <one-line description>"
puts $fd "#   PARAMS: (only params w/ options or ranges; default shown)"
puts $fd "#     <param>=<default>  {opt1,opt2,...}   or   \[min..max\]"
puts $fd ""

set idx 0
foreach ipdef $supported {
    incr idx
    set name   [get_property NAME $ipdef]
    set vlnv   [get_property VLNV $ipdef]
    set desc   [get_property DESCRIPTION $ipdef]
    set cats   [get_property TAXONOMY $ipdef]
    set disp   ""
    catch { set disp [get_property DISPLAY_NAME $ipdef] }

    # collapse whitespace in description
    regsub -all {\s+} $desc { } desc

    puts "($idx/$total) $name"

    puts $fd "### $name | $vlnv | $disp"
    puts $fd "CAT: $cats"
    puts $fd "DESC: $desc"

    # module name: alphanumeric only, no underscores (avoids __prefix bug)
    set mod "ipc$idx"
    if {[catch {
        create_ip -vlnv $vlnv -module_name $mod
        # create_ip returns file path; need the IP object via get_ips
        set inst [get_ips -quiet $mod]
        if {$inst eq ""} { error "get_ips returned empty after create_ip" }

        # config params - list_property needs a real IP object, not the XCI path
        set params [list_property $inst CONFIG.*]
        # skip low-value meta params common to all IPs
        set skip_patterns {Component_Name USE_BOARD_FLOW}
        set lines {}
        set opt_count 0
        foreach p [lsort $params] {
            set pname [string range $p 7 end]
            set skip 0
            foreach sp $skip_patterns {
                if {[string match $sp $pname]} { set skip 1; break }
            }
            if {$skip} { continue }
            set val [get_property $p $inst]
            set opts ""
            catch { set opts [list_property_value $p $inst] }
            # only mark options if >1 discrete choice (single-option = not a knob)
            set line "  $pname=$val"
            if {[llength $opts] > 1} {
                append line "  \{[join $opts ,]\}"
                incr opt_count
            }
            lappend lines $line
        }
        if {[llength $lines] > 0} {
            puts $fd "PARAMS:"
            foreach l $lines { puts $fd $l }
        }
        puts $fd "PARAM_COUNT: [llength $params] total, [llength $lines] shown, $opt_count with options"

        # cleanup so we don't accumulate state
        catch { remove_files -quiet [get_files -quiet "${mod}.xci"] }
        catch { file delete -force "$tmp_proj/ipcat.srcs/sources_1/ip/$mod" }
    } err]} {
        puts $fd "ERR: $err"
        catch { remove_files -quiet [get_files -quiet "${mod}.xci"] }
    }
    puts $fd ""
    flush $fd
}

close $fd
close_project
file delete -force $tmp_proj
puts "Done: $out_file ($total IPs)"
exit
