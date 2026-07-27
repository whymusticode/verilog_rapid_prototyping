
flatpak run com.github.corna.Vivado -mode tcl -source /home/me/REPOS/verilog_rapid_prototyping/ov7670/build.tcl   
flatpak run com.github.corna.Vivado -mode tcl -source /home/me/REPOS/verilog_rapid_prototyping/ov7670/program.tcl
flatpak run com.github.corna.Vivado -mode tcl -source  dump_ip_catalog.tcl

flatpak run com.github.corna.Vivado -mode tcl -source program_bitstream.tcl -tclargs "original_ov7670/FPGA-stereo-Camera-Basys3/Left_Right_Cam_(LeftCam).bit"
ok, so I was working on "original ov7670" which should be very similar except I   
  switched one cable I think, i moved a clock pin or smtg like that   

strace -f -e trace=openat,connect,execve -o ~/REPOS/verilog_rapid_prototyping/flatpak-trace.log flatpak run  com.github.corna.Vivado -mode tcl -source /dev/null 2>&1 | tail -30  