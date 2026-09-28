"""Complex magnitude sqrt(re^2 + im^2): two lanes in, one lane out.

Unlike mag2 this needs the square root, so it wants CORDIC vectoring or a
Newton iteration rather than a plain multiplier.
"""

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
    return np.abs(x)
