"""Quadrature downconverter: mix a real frame to complex baseband.

One lane in, two out. Needs a sine/cosine table and two multipliers.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

CYCLES_PER_FRAME = 4
PHASE = -2.0j * np.pi * CYCLES_PER_FRAME * np.arange(N) / N
CARRIER = np.exp(PHASE)


def target(x):
    return x * CARRIER
