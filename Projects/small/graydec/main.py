"""Gray code back to binary: a prefix-XOR across the byte."""

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
        binary = 0
        running = 0
        for bit in range(7, -1, -1):
            running ^= (value >> bit) & 1
            binary |= running << bit
        out.append(binary)
    return np.array(out, dtype=float)
