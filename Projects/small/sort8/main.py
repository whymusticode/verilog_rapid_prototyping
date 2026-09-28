"""Sort each group of eight samples ascending: a bitonic sorting network."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GROUP = 8


def target(x):
    return np.sort(x.reshape(-1, GROUP), axis=1).ravel()
