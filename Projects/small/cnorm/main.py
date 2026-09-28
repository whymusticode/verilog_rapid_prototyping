"""Normalise each complex sample to unit magnitude, leaving zeros alone."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def inputs(rng, frames):
    return [rng.uniform(-1, 1, N) + 1j * rng.uniform(-1, 1, N)
            for _ in range(frames)]


def target(x):
    magnitude = np.abs(x)
    return x / np.where(magnitude < 1e-9, 1.0, magnitude)
