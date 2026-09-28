"""Two-branch polyphase decomposition of a low-pass: one lane per phase."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

KERNEL = np.array([0.1, 0.2, 0.3, 0.2, 0.1, 0.05, 0.03, 0.02])


def target(x):
    filtered = np.convolve(x, KERNEL)[:N]
    return np.stack((filtered, np.concatenate(([0.0], filtered[:-1]))), axis=1)
