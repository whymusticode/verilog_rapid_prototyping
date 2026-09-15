#!/usr/bin/env python3
"""Emit the PFB coefficient ROM image used by a future RTL implementation."""

from __future__ import annotations

from pathlib import Path

import yaml

from pfb_reference import prototype_taps, quantize_coefficients


def main() -> None:
    directory = Path(__file__).parent
    params = yaml.safe_load((directory / "params.yaml").read_text())
    taps = prototype_taps(
        int(params["N"]), int(params["taps_per_phase"]), float(params["kaiser_beta"])
    )
    width = int(params["coefficient_bits"])
    values = quantize_coefficients(taps, width)
    mask = (1 << width) - 1
    # One word per [tap, phase], matching the matrix indexing in pfb_reference.
    output = directory / "pfb_coeffs_q1.mem"
    output.write_text("\n".join(f"{int(value) & mask:0{(width + 3) // 4}x}" for value in values.ravel()) + "\n")
    print(output)


if __name__ == "__main__":
    main()
