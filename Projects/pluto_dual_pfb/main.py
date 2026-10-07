"""Reference entry point for a dual-RX, 64-way Pluto PFB candidate.

``generate(samples)`` is the stream sim.py measures: one input sample is a
complex sample from each of the two receivers; the channelizer runs
continuously from one reset, so each 64-sample block's 64 x 2 channel outputs
are determined once that block has arrived. ``target(x)`` is one block after
reset, for interactive use.
"""

from pathlib import Path
import sys

import numpy as np
import yaml

PROJECT_DIRECTORY = Path(__file__).parent
# vrp.load_reference executes this file from an import spec, rather than as a
# package.  Make this project directory available in both that mode and normal
# ``python main.py`` use, without relying on the caller's current directory.
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from pfb_reference import PolyphaseChannelizer


with (PROJECT_DIRECTORY / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])
RX_COUNT = int(params["rx_count"])
TAPS_PER_PHASE = int(params["taps_per_phase"])
KAISER_BETA = float(params["kaiser_beta"])


def _frame(x: np.ndarray) -> np.ndarray:
    """Accept the harness's flat vector or explicit [sample, rx] frame."""
    value = np.asarray(x, dtype=np.complex128)
    if value.shape == (N, RX_COUNT):
        return value
    if value.ndim == 1 and value.size == N * RX_COUNT:
        return value.reshape(N, RX_COUNT)
    raise ValueError(f"expected ({N}, {RX_COUNT}) complex input samples, got {value.shape}")


def target(x: np.ndarray) -> np.ndarray:
    """Verilog-rapid-prototyping target wrapper: one reset PFB frame in/out."""
    pfb = PolyphaseChannelizer(N, TAPS_PER_PHASE, KAISER_BETA)
    return pfb.process(_frame(x))


def generate(samples: int) -> dict:
    """Random dual-RX samples in +-0.25 (each of I, Q) and the channelizer output."""
    rng = np.random.default_rng()
    frames = -(-samples // N)
    x = rng.uniform(-0.25, 0.25, (frames * N, RX_COUNT)) + 1j * rng.uniform(-0.25, 0.25, (frames * N, RX_COUNT))
    pfb = PolyphaseChannelizer(N, TAPS_PER_PHASE, KAISER_BETA)
    y = np.concatenate([pfb.process(x[f * N:(f + 1) * N]) for f in range(frames)])
    return dict(x=x, y=y, ready=np.repeat((np.arange(frames) + 1) * N, N))
