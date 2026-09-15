"""Reference entry point for a dual-RX, 64-way Pluto PFB candidate.

``target(x)`` is intentionally the thin wrapper expected by ``sim.py``.
It is stateless per invocation because each harness vector is an independent
reset-to-output transaction.  Use ``PolyphaseChannelizer.process`` directly
when checking continuous streaming frames.
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
TARGET_FREQUENCY = int(params["target"]["frequency"])
TARGET_CYCLES = int(params["target"]["cycles"])

if TARGET_FREQUENCY <= 0 or TARGET_CYCLES <= 0:
    raise ValueError("target.frequency and target.cycles must both be positive")


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


def stream(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Reference for frames streamed back to back after a single reset.

    A polyphase filter bank carries ``taps_per_phase - 1`` frames of FIR
    history, so hardware that runs continuously does not reproduce
    ``target`` for any frame but the first.  The streaming harness compares
    against this instead: one channelizer, reset once, fed every frame in
    order, exactly as the RTL sees them.
    """
    pfb = PolyphaseChannelizer(N, TAPS_PER_PHASE, KAISER_BETA)
    return [pfb.process(_frame(frame)) for frame in frames]


def inputs(rng: np.random.Generator, count: int) -> list[np.ndarray]:
    """Generate independent dual-RX complex frame transactions for sim.py."""
    return [
        rng.uniform(-0.25, 0.25, (N, RX_COUNT))
        + 1j * rng.uniform(-0.25, 0.25, (N, RX_COUNT))
        for _ in range(count)
    ]
