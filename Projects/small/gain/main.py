"""Scale every sample by a constant: one multiplier, no state."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def target(x):
    return 0.5 * x
