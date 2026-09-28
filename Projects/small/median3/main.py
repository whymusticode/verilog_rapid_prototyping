"""Three-tap median filter: a sorting network of three comparators."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    padded = np.concatenate(([0.0, 0.0], x))
    return np.array([np.median(padded[n:n + 3]) for n in range(N)])
