"""Pure eight-sample delay: a shift register, or one small RAM."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

DELAY = 8


def target(x):
    return np.concatenate((np.zeros(DELAY), x))[:N]
