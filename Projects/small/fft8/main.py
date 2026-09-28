"""Eight-point complex FFT per block: three radix-2 stages and a
twiddle ROM, scaled by 1/8."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def inputs(rng, frames):
    return [rng.uniform(-1, 1, N) + 1j * rng.uniform(-1, 1, N)
            for _ in range(frames)]


BLOCK = 8


def target(x):
    return np.fft.fft(x.reshape(-1, BLOCK), axis=1).ravel() / BLOCK
