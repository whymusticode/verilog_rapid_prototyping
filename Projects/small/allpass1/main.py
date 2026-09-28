"""First-order all-pass: flat magnitude, frequency-dependent delay."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

COEFF = 0.5


def target(x):
    y = np.zeros(N)
    previous_x = previous_y = 0.0
    for n in range(N):
        previous_y = -COEFF * x[n] + previous_x + COEFF * previous_y
        previous_x = x[n]
        y[n] = previous_y
    return y
