"""First-order IIR smoother y[n] = 0.875*y[n-1] + 0.125*x[n], y[-1] = 0.

Both coefficients are powers of two, so no multiplier is needed - but the
feedback loop cannot be pipelined away, which is what makes it interesting.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

DECAY = 0.875


def target(x):
    y = np.empty_like(x)
    accumulator = 0.0
    for index, sample in enumerate(x):
        accumulator = DECAY * accumulator + (1.0 - DECAY) * sample
        y[index] = accumulator
    return y
