#!/bin/sh
# Fix Vivado 2025.2.1 flatpak wrapper issues
# The flatpak expects old-style directory layout but 2025.2.1 changed it

INSTALL="/home/me/.var/app/com.github.corna.Vivado/data/xilinx-install"
VER="2025.2.1"

# Symlink .settings64*.sh files up one level (flatpak find uses maxdepth 3)
for f in "$INSTALL/$VER"/Vivado/.settings64*.sh \
         "$INSTALL/$VER"/Vitis/.settings64*.sh \
         "$INSTALL/$VER"/Model_Composer/.settings64*.sh; do
    [ -f "$f" ] && ln -sf "$f" "$INSTALL/$VER/$(basename "$f")"
done

# Symlink old-style path layout: <install>/Vivado/<ver>/ -> <install>/<ver>/Vivado/
mkdir -p "$INSTALL/Vivado"
ln -sfn "$INSTALL/$VER/Vivado" "$INSTALL/Vivado/$VER"

echo "Done. Vivado flatpak should now launch correctly."
