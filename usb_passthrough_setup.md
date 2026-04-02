# USB passthrough for Basys3 + Vivado Docker on Mac

brew install libusb
pip install usbipd
sudo usbipd bind --bus-id 0-1.1.4
sudo usbipd start

docker run --rm -v /Users/mbenton/Desktop/basys:/workspace -w /workspace --privileged --pid=host vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado -mode batch -source list_hw.tcl

docker run --rm -v $(pwd):/workspace -w /workspace --privileged --pid=host vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado -mode batch -source cordic_sin/program.tcl

docker run --rm -v $(pwd):/workspace -w /workspace vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado -mode batch -source matmul_10x10/build.tcl

docker run --rm -v $(pwd):/workspace -w /workspace --privileged --pid=host vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado -mode batch -source matmul_10x10/program.tcl


docker run --rm -v $(pwd):/workspace -w /workspace --privileged --pid=host vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado -mode batch -source cordic_sin/program.tcl