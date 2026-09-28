"""Real in, analytic signal out: a Hilbert-transforming FIR on the
imaginary lane and a matching delay on the real one."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

TAPS = 15
_n = np.arange(TAPS) - (TAPS - 1) // 2
_ideal = np.where(_n == 0, 0.0, (1 - np.cos(np.pi * _n)) / (np.pi * np.where(_n == 0, 1, _n)))
HILBERT = _ideal * np.hamming(TAPS)
DELAY = (TAPS - 1) // 2


def target(x):
    real = np.concatenate((np.zeros(DELAY), x))[:N]
    imag = np.convolve(x, HILBERT)[:N]
    return (real + 1j * imag) / 2.0
