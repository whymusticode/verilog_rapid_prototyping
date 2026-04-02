set script_dir [file normalize [file dirname [info script]]]
cd $script_dir

if {![file exists "$script_dir/sim_ds_pixels.mem"]} {
  puts "ERROR: sim_ds_pixels.mem missing. Run python exporter first."
  exit 1
}

set xilinx_bin "/opt/Xilinx/Vivado/2024.1/bin"
exec "$xilinx_bin/xvlog" "$script_dir/blob_bg_model_qvga.v" "$script_dir/tb_blob_bg_model.v"
exec "$xilinx_bin/xelab" tb_blob_bg_model -s tb_blob_bg_model
exec "$xilinx_bin/xsim" tb_blob_bg_model -runall
exit
