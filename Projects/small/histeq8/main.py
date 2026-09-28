"""Order statistics as a transfer curve: map each sample to its
empirical CDF within the frame."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return (np.argsort(np.argsort(x)) + 0.5) / N
