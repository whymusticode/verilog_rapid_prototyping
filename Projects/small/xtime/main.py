"""Multiply by two in GF(2^8) with the AES polynomial 0x11B:
a shift and a conditional XOR."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

def target(x):
    out = []
    for value in x.astype(int):
        shifted = (value << 1) & 0xFF
        out.append(shifted ^ 0x1B if value & 0x80 else shifted)
    return np.array(out, dtype=float)
