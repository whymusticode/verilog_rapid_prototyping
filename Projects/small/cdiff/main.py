"""Complex first difference: the phase-difference front end of a
demodulator, before the angle is taken."""

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
    return x * np.conj(np.concatenate(([0j], x[:-1])))/2.0
