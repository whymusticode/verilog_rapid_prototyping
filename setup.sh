#!/usr/bin/env bash
set -euo pipefail

./py2v/docker/build_vitis_image.sh "$@"


# to update vivado install:
# edit 
/home/mbenton/Xilinx/.xinstall/2025.2/xsetup -b AuthTokenGen
/home/mbenton/Xilinx/.xinstall/2025.2/xsetup -b Add -c /home/mbenton/.Xilinx/install_config.txt --agree XilinxEULA,3rdPartyEULA
