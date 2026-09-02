import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def bit_reverse_indices(n):
    """Return the bit-reversal permutation for 2**n points."""
    idx = np.arange(2**n, dtype=np.uint32)
    rev = np.zeros_like(idx)
    for i in range(n):
        rev = (rev << 1) | ((idx >> i) & 1)
    return rev


idx = bit_reverse_indices(int(np.log2(N)))
def target(x):
    y = np.fft.fft(x)
    return y[idx]


for i in range(10):
    target(np.random.rand(N) + 1j*np.random.rand(N))

