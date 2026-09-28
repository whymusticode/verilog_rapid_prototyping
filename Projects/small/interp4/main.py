"""Linear interpolation between every fourth sample."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

RATE = 4


def target(x):
    knots = np.concatenate((x[::RATE], [x[-1]]))
    positions = np.arange(N) / RATE
    return np.interp(positions, np.arange(len(knots)), knots)
