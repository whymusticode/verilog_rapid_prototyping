"""Scale each block of eight by its own peak: eight independent dividers,
or one shared and time-multiplexed."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GROUP = 8


def target(x):
    blocks = x.reshape(-1, GROUP)
    peaks = np.max(np.abs(blocks), axis=1)[:, None]
    return (blocks / np.where(peaks == 0, 1.0, peaks)).ravel()
