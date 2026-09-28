"""Eight-point DCT-II per block, the JPEG transform.

The matrix factors into a butterfly network: adds, subtracts and a few
constant multiplies, not sixty-four products."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

SIZE = 8
_k = np.arange(SIZE)
MATRIX = np.cos(np.pi * (2 * _k[None, :] + 1) * _k[:, None] / (2 * SIZE))
MATRIX[0] /= np.sqrt(2)
MATRIX *= np.sqrt(2.0 / SIZE)


def target(x):
    return (x.reshape(-1, SIZE) @ MATRIX.T).ravel() / np.sqrt(SIZE)
