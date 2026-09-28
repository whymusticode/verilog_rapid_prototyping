"""Replace each sample by its rank within its group of eight, scaled to [0,1)."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GROUP = 8


def target(x):
    blocks = x.reshape(-1, GROUP)
    return np.argsort(np.argsort(blocks, axis=1), axis=1).ravel() / GROUP
