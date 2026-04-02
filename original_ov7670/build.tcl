set proj_dir [file normalize [file dirname [info script]]]
set proj_name stereo_cam
create_project $proj_name $proj_dir/$proj_name -part xc7a35tcpg236-1 -force

set rtl_files [glob $proj_dir/rtl/*.vhd]
foreach f $rtl_files { add_files -fileset sources_1 $f }
add_files -fileset constrs_1 $proj_dir/Basys3.xdc

# frame_buffer: Simple Dual Port BRAM, 76800 x 4-bit (320*240 grayscale)
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.* \
  -module_name frame_buffer
set_property -dict [list \
  CONFIG.Memory_Type                   {Simple_Dual_Port_RAM} \
  CONFIG.Assume_Synchronous_Clk        {false} \
  CONFIG.Write_Width_A                 {4} \
  CONFIG.Write_Depth_A                 {76800} \
  CONFIG.Read_Width_B                  {4} \
  CONFIG.Enable_B                      {Use_ENB_Pin} \
  CONFIG.Register_PortB_Output_of_Memory_Primitives {true} \
  CONFIG.Port_B_Clock                  {100} \
  CONFIG.Port_B_Enable_Rate            {100} \
] [get_ips frame_buffer]
generate_target all [get_ips frame_buffer]

set_property top StereoCam [current_fileset]
set_property file_type {VHDL} [get_files *.vhd]

update_compile_order -fileset sources_1

launch_runs synth_1 -jobs 4
wait_on_run synth_1
if { [get_property PROGRESS [get_runs synth_1]] != "100%" } { error "Synth failed" }

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if { [get_property PROGRESS [get_runs impl_1]] != "100%" } { error "Impl failed" }

set rpt_dir $proj_dir/$proj_name/${proj_name}.runs/impl_1
puts "Bitstream: $rpt_dir/StereoCam.bit"
puts "Resource %%: $rpt_dir/utilization.rpt (LUT/FF/DSP/BRAM)"
exit
