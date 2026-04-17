#!/bin/sh
# Install Xilinx/Digilent udev rules for FPGA JTAG access
# Run as: sudo sh install_udev_rules.sh

SRC="/home/me/.var/app/com.github.corna.Vivado/data/xilinx-install/2025.2.1/data/xicom/cable_drivers/lin64/install_script/install_drivers"
sudo cp "$SRC/52-xilinx-ftdi-usb.rules" /etc/udev/rules.d/
sudo cp "$SRC/52-xilinx-digilent-usb.rules" /etc/udev/rules.d/
sudo cp "$SRC/52-xilinx-pcusb.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "Done. Unplug and replug the board."

# NixOS: add the following to your configuration.nix instead, then nixos-rebuild switch
#
# services.udev.extraRules = ''
#     ATTRS{idVendor}=="0403", ATTRS{bInterfaceNumber}=="00", PROGRAM="/bin/sh -c 'echo -n $id:1.0 > /sys/bus/usb/drivers/ftdi_sio/unbind; echo -n $id:1.1 > /sys/bus/usb/drivers/ftdi_sio/unbind'"
#     ACTION=="add", ATTRS{idVendor}=="0403", MODE:="666"
#     ATTRS{idVendor}=="1443", MODE:="666"
#     ACTION=="add", ATTRS{idVendor}=="0403", ATTRS{manufacturer}=="Digilent", MODE:="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="0008", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="0007", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="0009", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="000d", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="000f", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="0013", MODE="666"
#     ATTR{idVendor}=="03fd", ATTR{idProduct}=="0015", MODE="666"
# '';
