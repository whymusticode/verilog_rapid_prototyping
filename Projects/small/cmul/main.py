"""Multiply by a fixed complex constant: three multipliers with the
Karatsuba trick, four without."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def inputs(rng, frames):
    return [rng.uniform(-1, 1, N) + 1j * rng.uniform(-1, 1, N)
            for _ in range(frames)]


CONSTANT = 0.6 + 0.5j


def target(x):
    return x * CONSTANT
