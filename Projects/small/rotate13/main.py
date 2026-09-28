"""Circularly rotate the frame by thirteen samples."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

SHIFT = 13


def target(x):
    return np.roll(x, SHIFT)
