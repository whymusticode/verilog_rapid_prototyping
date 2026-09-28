"""Double dabble: binary to packed BCD, three digits of four bits each.
A shift-and-add-three loop in Python; a fixed comparator chain in RTL."""

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
        register = value
        for _ in range(8):
            for offset in (8, 12, 16):
                if ((register >> offset) & 0xF) >= 5:
                    register += 3 << offset
            register <<= 1
        out.append((register >> 8) & 0xFFF)
    return np.array(out, dtype=float)
