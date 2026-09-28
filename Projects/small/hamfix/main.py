"""Treat the low seven bits as a Hamming(7,4) word, locate any single-bit
error from the syndrome and correct it."""

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
        bits = [(value >> position) & 1 for position in range(7)]
        s0 = bits[0] ^ bits[1] ^ bits[3] ^ bits[4]
        s1 = bits[0] ^ bits[2] ^ bits[3] ^ bits[5]
        s2 = bits[1] ^ bits[2] ^ bits[3] ^ bits[6]
        syndrome = s0 | (s1 << 1) | (s2 << 2)
        position = {0: None, 1: 4, 2: 5, 3: 0, 4: 6, 5: 1, 6: 2, 7: 3}[syndrome]
        if position is not None:
            bits[position] ^= 1
        out.append(sum(bit << index for index, bit in enumerate(bits)))
    return np.array(out, dtype=float)
