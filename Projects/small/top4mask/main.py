"""Keep the four largest samples in each group of eight, zero the rest."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

GROUP = 8
KEEP = 4


def target(x):
    blocks = x.reshape(-1, GROUP).copy()
    threshold = np.sort(blocks, axis=1)[:, -KEEP][:, None]
    return np.where(blocks >= threshold, blocks, 0.0).ravel()
