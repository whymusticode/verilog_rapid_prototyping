"""Running CRC-8 (polynomial 0x07) over the frame, emitted after every
byte and cleared at each frame boundary. Eight serial steps in Python;
one XOR matrix in hardware."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

POLY = 0x07


def target(x):
    crc = 0
    out = []
    for byte in x.astype(int):
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ POLY) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        out.append(crc)
    return np.array(out, dtype=float)
