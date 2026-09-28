"""Split the frame into even and odd samples, evens first."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return np.concatenate((x[0::2], x[1::2]))
