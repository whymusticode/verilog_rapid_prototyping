"""Binary to Gray code, b ^ (b >> 1). The encoding every asynchronous
FIFO pointer uses so a mid-flight sample can only be off by one."""

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
    return np.array([int(b) ^ (int(b) >> 1) for b in x], dtype=float)
