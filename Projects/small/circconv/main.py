"""Circular convolution of each block of sixteen with a fixed kernel."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

BLOCK = 16
KERNEL = np.array([0.5, 0.25, 0.125, 0.0625] + [0.0] * (BLOCK - 4))


def target(x):
    blocks = x.reshape(-1, BLOCK)
    spectrum = np.fft.fft(blocks, axis=1) * np.fft.fft(KERNEL)
    return np.real(np.fft.ifft(spectrum, axis=1)).ravel()
