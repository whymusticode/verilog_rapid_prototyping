"""The AES S-box, derived rather than tabulated: multiplicative inverse
in GF(2^8) followed by the affine transform. Complicated to describe,
and a single 256-entry ROM to build."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

def _gf_mul(a, b):
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return result


def _inverse(value):
    if value == 0:
        return 0
    for candidate in range(1, 256):
        if _gf_mul(value, candidate) == 1:
            return candidate
    return 0


def _sbox(value):
    inverted = _inverse(value)
    result = inverted
    for shift in (1, 2, 3, 4):
        result ^= ((inverted << shift) | (inverted >> (8 - shift))) & 0xFF
    return result ^ 0x63


TABLE = [_sbox(value) for value in range(256)]


def target(x):
    return np.array([TABLE[int(b)] for b in x], dtype=float)
