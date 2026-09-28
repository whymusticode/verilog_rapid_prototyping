"""Apply a Hann window to the frame: a coefficient ROM and one multiplier."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

WINDOW = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(N) / N)


def target(x):
    return x * WINDOW
