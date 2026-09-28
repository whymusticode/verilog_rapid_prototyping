"""The SHA-256 sigma mixing function, narrowed to a byte:
ROTR1 ^ ROTR4 ^ SHR2. Rotations are free in hardware."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

def _rotr(value, amount):
    return ((value >> amount) | (value << (8 - amount))) & 0xFF


def target(x):
    return np.array([_rotr(int(b), 1) ^ _rotr(int(b), 4) ^ (int(b) >> 2)
                     for b in x], dtype=float)
