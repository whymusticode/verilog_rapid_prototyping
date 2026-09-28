"""Read the frame as an 8x8 matrix and transpose it."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

SIDE = 8


def target(x):
    return x.reshape(SIDE, SIDE).T.ravel()
