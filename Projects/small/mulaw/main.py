"""Mu-law companding, the telephony compressor. Logarithmic, so a
leading-zero count plus a small mantissa LUT does most of the work."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

MU = 255.0


def target(x):
    return np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
