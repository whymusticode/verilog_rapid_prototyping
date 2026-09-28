"""Square root of the magnitude: CORDIC, Newton, or a shift-and-subtract loop."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

def target(x):
    return np.sqrt(np.abs(x))
