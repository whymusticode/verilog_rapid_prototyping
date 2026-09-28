"""Bit-reversal permutation of the frame: the addressing an FFT needs.

No arithmetic at all, but the whole frame must be buffered and read back
in a permuted order without stalling the stream.
"""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def bit_reverse_indices(bits):
    index = np.arange(2 ** bits, dtype=np.uint32)
    reversed_index = np.zeros_like(index)
    for position in range(bits):
        reversed_index = (reversed_index << 1) | ((index >> position) & 1)
    return reversed_index


ORDER = bit_reverse_indices(int(np.log2(N)))


def target(x):
    return x[ORDER]
