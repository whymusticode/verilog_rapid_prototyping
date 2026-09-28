"""DC blocker: a differentiator followed by a leaky integrator."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

POLE = 0.995


def target(x):
    y = np.zeros(N)
    previous_x = previous_y = 0.0
    for n in range(N):
        previous_y = x[n] - previous_x + POLE * previous_y
        previous_x = x[n]
        y[n] = previous_y
    return y
