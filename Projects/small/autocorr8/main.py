"""Circular autocorrelation of each block of eight, normalised by the block."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

BLOCK = 8


def target(x):
    blocks = x.reshape(-1, BLOCK)
    lags = [np.sum(blocks * np.roll(blocks, -lag, axis=1), axis=1) for lag in range(BLOCK)]
    return np.stack(lags, axis=1).ravel() / BLOCK
