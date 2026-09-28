"""Saturate samples to +/-0.5: compare and select, no multiplier at all."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def target(x):
    return np.clip(x, -0.5, 0.5)
