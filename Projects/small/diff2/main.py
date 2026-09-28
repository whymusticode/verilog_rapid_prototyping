"""Second difference: two cascaded differentiators."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return np.diff(x, n=2, prepend=0.0, append=0.0)[:N]
