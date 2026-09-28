"""Additive scrambler: XOR each byte with eight bits of a PRBS-7
sequence (x^7 + x^6 + 1), restarted every frame."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

SEED = 0x7F


def target(x):
    state = SEED
    out = []
    for byte in x.astype(int):
        mask = 0
        for bit in range(8):
            feedback = ((state >> 6) ^ (state >> 5)) & 1
            state = ((state << 1) | feedback) & 0x7F
            mask |= feedback << bit
        out.append(int(byte) ^ mask)
    return np.array(out, dtype=float)
