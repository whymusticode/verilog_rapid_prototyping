"""Gamma encode with exponent 0.45, the display transfer curve."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GAMMA = 0.45


def target(x):
    return np.sign(x) * np.abs(x) ** GAMMA
