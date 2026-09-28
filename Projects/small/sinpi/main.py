"""Sine of pi*x over a full period: quarter-wave symmetry halves the ROM twice."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return np.sin(np.pi * x)
