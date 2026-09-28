"""Thirty-one tap windowed-sinc low-pass FIR, zero-padded at frame start.

The cycle budget allows two clocks per sample, so a single multiply-
accumulate cannot keep up: the taps have to be folded or run in parallel.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

TAPS = 31
_n = np.arange(TAPS) - (TAPS - 1) / 2
_sinc = np.sinc(_n / 4.0)
_hamming = 0.54 - 0.46 * np.cos(2.0 * np.pi * np.arange(TAPS) / (TAPS - 1))
COEFFS = _sinc * _hamming
COEFFS = COEFFS / COEFFS.sum()


def target(x):
    return np.convolve(x, COEFFS)[:N]
