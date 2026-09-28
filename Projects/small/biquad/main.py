"""Direct-form-I biquad low-pass, cleared at each frame boundary.

Two poles in the feedback path: the loop sets the achievable clock rate."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

B = np.array([0.0976, 0.1953, 0.0976])
A = np.array([1.0, -0.9428, 0.3333])


def target(x):
    y = np.zeros(N)
    x1 = x2 = y1 = y2 = 0.0
    for n in range(N):
        acc = B[0] * x[n] + B[1] * x1 + B[2] * x2 - A[1] * y1 - A[2] * y2
        x2, x1 = x1, x[n]
        y2, y1 = y1, acc
        y[n] = acc
    return y
