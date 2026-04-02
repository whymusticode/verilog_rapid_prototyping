set proj_dir [file normalize [file dirname [info script]]]
exec /opt/Xilinx/Vivado/2024.1/bin/xvlog -sv $proj_dir/rtl/uart_rx.v \
                                           $proj_dir/rtl/uart_tx.v \
                                           $proj_dir/rtl/complex_mul_3dsp.v \
                                           $proj_dir/rtl/cmatmul10x10_dsp.v \
                                           $proj_dir/rtl/pivot_pairs_10x10.v \
                                           $proj_dir/rtl/jacobi_sweep10x10.v \
                                           $proj_dir/rtl/jacobi_engine10x10.v \
                                           $proj_dir/sim/tb_jacobi_engine_converge.v
exec /opt/Xilinx/Vivado/2024.1/bin/xelab tb_jacobi_engine_converge -s tb_jacobi_engine_converge_sim -debug typical
exec /opt/Xilinx/Vivado/2024.1/bin/xsim tb_jacobi_engine_converge_sim -runall
quit
