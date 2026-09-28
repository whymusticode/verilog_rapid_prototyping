"""Insert a zero between samples and low-pass: two output lanes per input."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

KERNEL = np.array([0.25, 0.5, 0.25])


def target(x):
    doubled = np.zeros(2 * N)
    doubled[0::2] = x
    filtered = np.convolve(doubled, KERNEL)[:2 * N]
    return filtered.reshape(N, 2)
