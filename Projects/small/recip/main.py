"""Reciprocal of x+2, so the divisor never approaches zero.

Newton-Raphson or a LUT with one correction step."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return 1.0 / (x + 2.0)
