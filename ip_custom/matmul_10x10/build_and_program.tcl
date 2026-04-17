# Build then program. For build-only use build.tcl; for program-only use program.tcl.
set proj_dir [file normalize [file dirname [info script]]]
source $proj_dir/build.tcl
source $proj_dir/program.tcl
