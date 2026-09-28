"""Manchester encode: every bit becomes two, so each byte leaves as two."""

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
        encoded = 0
        for bit in range(8):
            pair = 0b10 if (value >> bit) & 1 else 0b01
            encoded |= pair << (2 * bit)
        out.append((encoded & 0xFF, encoded >> 8))
    return np.array(out, dtype=float)
