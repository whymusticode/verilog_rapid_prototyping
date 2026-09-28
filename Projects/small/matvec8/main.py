"""Multiply each block of eight by a fixed 8x8 matrix: a small systolic array."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

SIZE = 8
MATRIX = np.cos(np.arange(SIZE)[:, None] * np.arange(SIZE)[None, :]) / SIZE


def target(x):
    return (x.reshape(-1, SIZE) @ MATRIX.T).ravel()
