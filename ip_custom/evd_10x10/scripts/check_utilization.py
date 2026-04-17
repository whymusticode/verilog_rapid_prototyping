from pathlib import Path
import re

RPT = Path(__file__).resolve().parents[1] / "utilization.rpt"


def extract(name, text):
    m = re.search(rf"\|\s*{name}\s*\|\s*([0-9,]+)\s*\|", text)
    return m.group(1) if m else "NA"


def main():
    txt = RPT.read_text()
    lut = extract("CLB LUTs", txt)
    reg = extract("CLB Registers", txt)
    dsp = extract("DSPs", txt)
    bram = extract("Block RAM Tile", txt)
    print(f"CLB_LUTs={lut}")
    print(f"CLB_Registers={reg}")
    print(f"DSPs={dsp}")
    print(f"BlockRAM={bram}")


if __name__ == "__main__":
    main()
