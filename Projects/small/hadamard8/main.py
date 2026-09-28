"""Eight-point Walsh-Hadamard transform: additions and subtractions only."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])

SIZE = 8


def _matrix(order):
    matrix = np.ones((1, 1))
    while matrix.shape[0] < order:
        matrix = np.block([[matrix, matrix], [matrix, -matrix]])
    return matrix


MATRIX = _matrix(SIZE)


def target(x):
    return (x.reshape(-1, SIZE) @ MATRIX.T).ravel() / SIZE
