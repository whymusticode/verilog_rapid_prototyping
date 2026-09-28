"""TMDS encoding from the HDMI specification: transition minimisation by
XOR or XNOR, then DC balancing against a running disparity counter that
persists across the frame. Ten bits out per byte in."""

import numpy as np
import yaml
from pathlib import Path


with (Path(__file__).parent / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

N = int(params["N"])


def inputs(rng, frames):
    """Whole bytes. params.yaml picks bits so FRAC is zero: tdata is the byte."""
    return [rng.integers(0, 256, N).astype(float) for _ in range(frames)]

def _popcount(value):
    return bin(value).count("1")


def target(x):
    disparity = 0
    out = []
    for value in x.astype(int):
        ones = _popcount(value)
        use_xnor = ones > 4 or (ones == 4 and (value & 1) == 0)
        q = value & 1
        word = q
        for bit in range(1, 8):
            q = (q ^ ((value >> bit) & 1) ^ 1) if use_xnor else (q ^ ((value >> bit) & 1))
            word |= q << bit
        flag = 0 if use_xnor else 1
        ones_q = _popcount(word)
        zeros_q = 8 - ones_q
        if disparity == 0 or ones_q == zeros_q:
            if flag:
                symbol = (0 << 9) | (1 << 8) | word
                disparity += ones_q - zeros_q
            else:
                symbol = (1 << 9) | (0 << 8) | (~word & 0xFF)
                disparity += zeros_q - ones_q
        elif (disparity > 0 and ones_q > zeros_q) or (disparity < 0 and zeros_q > ones_q):
            symbol = (1 << 9) | (flag << 8) | (~word & 0xFF)
            disparity += 2 * flag + zeros_q - ones_q
        else:
            symbol = (0 << 9) | (flag << 8) | word
            disparity += -2 * (1 - flag) + ones_q - zeros_q
        out.append(symbol)
    return np.array(out, dtype=float)
