"""Zero-order hold: sample every fourth input and hold it."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

RATE = 4


def target(x):
    return np.repeat(x[::RATE], RATE)[:N]
