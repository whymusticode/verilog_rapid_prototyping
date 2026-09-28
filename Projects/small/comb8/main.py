"""Feed-forward comb: y[n] = x[n] - x[n-8]. A shift register and a subtract."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

DELAY = 8


def target(x):
    delayed = np.concatenate((np.zeros(DELAY), x))[:N]
    return x - delayed
