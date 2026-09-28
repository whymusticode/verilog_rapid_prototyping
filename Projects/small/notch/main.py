"""Two-pole notch at one eighth of the sample rate."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

RADIUS = 0.9
ANGLE = 2.0 * np.pi / 8.0
B = np.array([1.0, -2.0 * np.cos(ANGLE), 1.0])
A = np.array([1.0, -2.0 * RADIUS * np.cos(ANGLE), RADIUS ** 2])


def target(x):
    y = np.zeros(N)
    x1 = x2 = y1 = y2 = 0.0
    for n in range(N):
        acc = B[0] * x[n] + B[1] * x1 + B[2] * x2 - A[1] * y1 - A[2] * y2
        x2, x1 = x1, x[n]
        y2, y1 = y1, acc
        y[n] = acc / 4.0
    return y
