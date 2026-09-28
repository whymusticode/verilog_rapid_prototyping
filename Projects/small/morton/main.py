"""Interleave the bits of the two nibbles: Z-order curve addressing."""

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
        low, high = value & 0xF, value >> 4
        result = 0
        for bit in range(4):
            result |= ((low >> bit) & 1) << (2 * bit)
            result |= ((high >> bit) & 1) << (2 * bit + 1)
        out.append(result)
    return np.array(out, dtype=float)
