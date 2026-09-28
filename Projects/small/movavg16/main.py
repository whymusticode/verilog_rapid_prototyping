"""Sixteen-tap boxcar. The efficient form is a running sum plus a
delay line, not sixteen adders."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

TAPS = 16


def target(x):
    return np.convolve(x, np.ones(TAPS) / TAPS)[:N]
