"""First difference y[n] = x[n] - x[n-1], with x[-1] taken as zero.

One sample of history, so the design needs a single register in the datapath.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def target(x):
    return np.diff(x, prepend=0.0)
