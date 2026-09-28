"""Peak detector with exponential decay: max against a leaking register."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

DECAY = 0.98


def target(x):
    y = np.zeros(N)
    peak = 0.0
    for n in range(N):
        peak = max(abs(x[n]), DECAY * peak)
        y[n] = peak
    return y
