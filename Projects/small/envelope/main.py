"""Envelope follower: rectify, then smooth with a one-pole low-pass."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

POLE = 0.9


def target(x):
    y = np.zeros(N)
    level = 0.0
    for n in range(N):
        level = POLE * level + (1.0 - POLE) * abs(x[n])
        y[n] = level
    return y
