"""Seven-segment decode of the low nibble, segments a..g in bits 0..6."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

SEGMENTS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
            0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]


def target(x):
    return np.array([SEGMENTS[int(b) & 0xF] for b in x], dtype=float)
