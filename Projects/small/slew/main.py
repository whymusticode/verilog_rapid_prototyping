"""Slew-rate limiter: the output may move by at most one eighth per sample."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

LIMIT = 0.125


def target(x):
    y = np.zeros(N)
    current = 0.0
    for n in range(N):
        current += np.clip(x[n] - current, -LIMIT, LIMIT)
        y[n] = current
    return y
