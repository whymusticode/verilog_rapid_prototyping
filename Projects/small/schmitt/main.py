"""Schmitt trigger: a one-bit output with hysteresis, held as +/-0.5."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

HIGH, LOW = 0.25, -0.25


def target(x):
    y = np.zeros(N)
    state = 0
    for n in range(N):
        if x[n] > HIGH:
            state = 1
        elif x[n] < LOW:
            state = 0
        y[n] = 0.5 if state else -0.5
    return y
