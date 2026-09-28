"""Running mean: the prefix sum of the frame, scaled by 1/N.

An accumulator and a shift. The accumulator has to be wider than the
samples, and has to reset on each frame boundary.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def target(x):
    return np.cumsum(x) / N
