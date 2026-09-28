"""Split each sample into coarse and fine halves on two output lanes."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    coarse = np.round(x * 16.0) / 16.0
    return np.stack((coarse, x - coarse), axis=1)
