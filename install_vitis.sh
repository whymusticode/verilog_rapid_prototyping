
INSTALLER=~/FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_1114_2157_Lin64.bin
DEST=/tmp/xi_extract
CFG=./py2v/install_config.txt

"$INSTALLER" --noexec --target "$DEST"

echo "1" | "$DEST/xsetup" -b ConfigGen 
# "$DEST/xsetup" --help
# Edit CFG


"$DEST/xsetup" -b AuthTokenGen

"$DEST/xsetup" --agree XilinxEULA,3rdPartyEULA --batch Install --config "$CFG"

sudo /home/mbenton/Xilinx/2025.2/Vitis/scripts/installLibs.sh
source /home/mbenton/Xilinx/2025.2/Vitis/settings64.sh

# oh shoot I foror something:
# Edit CFG
# then you have to use the installed xsetup:
# /home/mbenton/Xilinx/.xinstall/2025.2/xsetup --agree XilinxEULA,3rdPartyEULA --batch Add --config "$CFG"
