#!/bin/sh
# Vivado GUI from Docker. On Mac first:
#   brew install --cask xquartz
#   XQuartz: Preferences → Security → "Allow connections from network clients"
#   Log out and back in (or reboot). Then: xhost + localhost
#   Start usbipd and attach Basys if you need hardware.
set -e
cd "$(dirname "$0")"
xhost + localhost 2>/dev/null || true
docker run --rm -it \
  -e DISPLAY=host.docker.internal:0 \
  -v "$(pwd)":/workspace -w /workspace \
  --privileged --pid=host \
  vivado:latest /opt/Xilinx/Vivado/2024.1/bin/vivado
# TODO xquartz is busted so gui not comming up, but this does create a vivado Tcl interpreter REPL