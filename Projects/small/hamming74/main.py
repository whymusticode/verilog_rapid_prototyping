"""Hamming(7,4) encode of the low nibble: three parity bits appended."""

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
        d = [(value >> bit) & 1 for bit in range(4)]
        p0 = d[0] ^ d[1] ^ d[3]
        p1 = d[0] ^ d[2] ^ d[3]
        p2 = d[1] ^ d[2] ^ d[3]
        out.append(d[0] | d[1] << 1 | d[2] << 2 | d[3] << 3 | p0 << 4 | p1 << 5 | p2 << 6)
    return np.array(out, dtype=float)
