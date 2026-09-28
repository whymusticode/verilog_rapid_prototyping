"""Sixteen-sample running RMS: square, boxcar, square root."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

WINDOW = 16


def target(x):
    mean_square = np.convolve(x ** 2, np.ones(WINDOW) / WINDOW)[:N]
    return np.sqrt(mean_square)
