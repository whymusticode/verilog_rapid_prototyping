"""Requantise to sixteen levels: round to the nearest eighth."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return np.round(x * 8.0) / 8.0
