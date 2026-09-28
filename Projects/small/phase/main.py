"""Argument of a complex sample, scaled to [-1,1): CORDIC vectoring mode."""

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
    return np.angle(x) / np.pi
