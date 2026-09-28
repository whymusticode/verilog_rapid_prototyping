"""Eight-tap symmetric low-pass FIR, zero-padded at the start of each frame.

The usual first real DSP block: a short delay line and a multiply-accumulate.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

# Normalised so a full-scale input cannot overflow the accumulator.
TAPS = np.array([1.0, 3.0, 6.0, 10.0, 10.0, 6.0, 3.0, 1.0])
TAPS = TAPS / TAPS.sum()


def target(x):
    return np.convolve(x, TAPS)[:N]
