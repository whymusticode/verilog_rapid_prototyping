"""Differential coding across the frame, then a running reconstruction:
the encoder and decoder back to back must be the identity."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    residual = np.diff(x, prepend=0.0)
    return np.cumsum(residual)
