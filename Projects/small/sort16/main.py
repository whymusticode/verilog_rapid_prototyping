"""Sort each group of sixteen ascending: a larger bitonic network."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GROUP = 16


def target(x):
    return np.sort(x.reshape(-1, GROUP), axis=1).ravel()
