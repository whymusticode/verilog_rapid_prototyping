#!/usr/bin/env bash
set -euo pipefail

TAR_NAME="FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023.tar.gz"
EXTRACT_DIR="FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023"
CONTAINER_NAME="py2v-vitis-installer"
IMAGE_TAG="py2v-vitis:2024.1"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --platform linux/amd64 --name "$CONTAINER_NAME" -v "$HOME/Desktop:/mnt/desktop" -v "$HOME/.Xilinx:/root/.Xilinx" ubuntu:22.04 sleep infinity
docker exec "$CONTAINER_NAME" bash -lc 'apt-get update && apt-get install -y --no-install-recommends bash ca-certificates file libtinfo5 perl python3 tar xz-utils zlib1g-dev'
docker exec -it "$CONTAINER_NAME" bash -lc "cd /mnt/desktop && tar -xzf \"$TAR_NAME\""
docker exec -it "$CONTAINER_NAME" bash -lc "cd /mnt/desktop/$EXTRACT_DIR && ./xsetup -b AuthTokenGen"
docker exec -it "$CONTAINER_NAME" bash -lc "cd /mnt/desktop/$EXTRACT_DIR && ./xsetup --batch Install --agree XilinxEULA,3rdPartyEULA --product Vitis --edition \"Vitis Unified Software Platform\" --location /opt/Xilinx"
docker commit "$CONTAINER_NAME" "$IMAGE_TAG"
docker run --rm --platform linux/amd64 "$IMAGE_TAG" /opt/Xilinx/Vivado/2024.1/bin/vivado -version
