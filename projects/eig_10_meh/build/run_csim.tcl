open_project hls_csim_prj
set_top kernel_top
add_files hls/kernel.cpp
add_files -tb hls/tb.cpp
open_solution -reset csim
set_part {xczu7ev-ffvc1156-2-e}
create_clock -period 10.000 -name default
csim_design
exit
