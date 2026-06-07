#!/bin/sh
# Fix Vivado 2025.2.1 flatpak wrapper issues
# The flatpak expects old-style directory layout but 2025.2.1 changed it

# INSTALL="/home/me/.var/app/com.github.corna.Vivado/data/xilinx-install"
# VER="2025.2.1"

# # Symlink .settings64*.sh files up one level (flatpak find uses maxdepth 3)
# for f in "$INSTALL/$VER"/Vivado/.settings64*.sh \
#          "$INSTALL/$VER"/Vitis/.settings64*.sh \
#          "$INSTALL/$VER"/Model_Composer/.settings64*.sh; do
#     [ -f "$f" ] && ln -sf "$f" "$INSTALL/$VER/$(basename "$f")"
# done

# # Symlink old-style path layout: <install>/Vivado/<ver>/ -> <install>/<ver>/Vivado/
# mkdir -p "$INSTALL/Vivado"
# ln -sfn "$INSTALL/$VER/Vivado" "$INSTALL/Vivado/$VER"


INSTALL="$HOME/.var/app/com.github.corna.Vivado/data/xilinx-install"
VER="2025.2.1"
for tool in Vivado Vitis Vitis_HLS Model_Composer; do
    src="$INSTALL/$VER/$tool"
    [ -d "$src" ] || continue
    # 1) lift .settings64*.sh up one level (within maxdepth)
    for f in "$src"/.settings64*.sh; do
        [ -f "$f" ] && ln -sf "$f" "$INSTALL/$VER/$(basename "$f")"
    done
    # 2) recreate classic <install>/<Tool>/<ver> layout for every tool
    mkdir -p "$INSTALL/$tool"
    ln -sfn "$src" "$INSTALL/$tool/$VER"
done