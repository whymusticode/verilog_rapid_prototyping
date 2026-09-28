"""Magnitude squared of a complex frame: two lanes in, one lane out.

Exercises IN_LANES=2 with OUT_LANES=1 and needs no square root.
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
    return (x.real ** 2 + x.imag ** 2)
