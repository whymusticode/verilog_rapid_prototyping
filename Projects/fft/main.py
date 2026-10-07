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
    """One N-point FFT, output in bit-reversed order."""
    y = np.fft.fft(x)
    return y[idx]


def generate(samples):
    """Back-to-back N-point frames of random complex samples in [0, 1).

    Each frame's N outputs are determined once that frame's N inputs arrived.
    """
    rng = np.random.default_rng()
    frames = -(-samples // N)
    x = rng.random((frames, N)) + 1j * rng.random((frames, N))
    y = np.concatenate([target(frame) for frame in x])
    return dict(x=x.ravel(), y=y, ready=np.repeat((np.arange(frames) + 1) * N, N))
