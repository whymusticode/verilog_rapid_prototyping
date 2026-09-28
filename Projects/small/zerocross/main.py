"""Flag every sign change: one register and an XOR of sign bits."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    signs = np.signbit(x)
    previous = np.concatenate(([signs[0]], signs[:-1]))
    return (signs != previous).astype(float)
