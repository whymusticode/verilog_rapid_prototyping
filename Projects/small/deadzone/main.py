"""Zero out anything smaller than a quarter, pass the rest untouched."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

THRESHOLD = 0.25


def target(x):
    return np.where(np.abs(x) < THRESHOLD, 0.0, x)
