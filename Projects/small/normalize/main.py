"""Scale the frame so its largest magnitude becomes one.

Two passes over the frame: find the peak, then divide. Needs a frame
buffer and a reciprocal, and ping-pong buffering to keep throughput up.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def target(x):
    return x / np.max(np.abs(x))
