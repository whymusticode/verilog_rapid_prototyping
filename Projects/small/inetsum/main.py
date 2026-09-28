"""The internet checksum: a running one's-complement sum of the bytes
with end-around carry, cleared each frame."""

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
    total = 0
    out = []
    for byte in x.astype(int):
        total += byte
        total = (total & 0xFFFF) + (total >> 16)
        out.append(total)
    return np.array(out, dtype=float)
