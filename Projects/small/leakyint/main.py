"""Leaky integrator with unit DC gain: the classic single-pole accumulator."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

POLE = 0.99


def target(x):
    y = np.zeros(N)
    state = 0.0
    for n in range(N):
        state = POLE * state + (1.0 - POLE) * x[n]
        y[n] = state
    return y
