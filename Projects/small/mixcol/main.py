"""One AES MixColumns column per group of four bytes: the fixed GF(2^8)
matrix [[2,3,1,1],[1,2,3,1],[1,1,2,3],[3,1,1,2]]."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

def _xtime(value):
    shifted = (value << 1) & 0xFF
    return shifted ^ 0x1B if value & 0x80 else shifted


def _column(a):
    total = a[0] ^ a[1] ^ a[2] ^ a[3]
    return [a[i] ^ total ^ _xtime(a[i] ^ a[(i + 1) % 4]) for i in range(4)]


def target(x):
    values = x.astype(int).reshape(-1, 4)
    return np.array([byte for column in values for byte in _column(list(column))],
                    dtype=float)
