"""Correct IQ gain and quadrature imbalance: a 2x2 real matrix on the lanes."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def inputs(rng, frames):
    return [rng.uniform(-1, 1, N) + 1j * rng.uniform(-1, 1, N)
            for _ in range(frames)]


GAIN = 1.08
SKEW = 0.05


def target(x):
    real = x.real
    imag = GAIN * (x.imag + SKEW * x.real)
    return (real + 1j * imag) / 1.2
