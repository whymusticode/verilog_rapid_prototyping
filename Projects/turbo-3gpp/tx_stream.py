"""Transmitter and channel for the continuous stream: what the Pluto ADC sees.

The receiver's noise floor is fixed (NOISE_RMS ADC codes per complex sample).
Each burst arrives after an idle gap with its own power (set by an Es/N0
operating point), carrier frequency offset, carrier phase and fractional
delay. The sum is rounded and saturated to 12-bit codes.
"""
import numpy as np
from turbo_3gpp import core
import rx_phy
import rx_stream

NOISE_RMS = 16
RATES = (1 / 3, 1 / 2, 2 / 3, 3 / 4, 5 / 6)
MIN_GAP = 32                                  # idle samples between bursts
CFO_RANGE = np.pi / len(rx_phy.SEGMENT)       # receiver's CFO range, rad/symbol


def geometry(A, q_m, rate):
    """G for payload A at about `rate`, divisible by C*Q_m (rate matching)."""
    C = len(core.get_3gpp_code_block_segment_lengths(A + 24))
    unit = C * q_m
    return int(np.ceil((A + 24) / rate / unit)) * unit


def burst_length(A, q_m, rate):
    return rx_stream.SPS * rx_stream.burst_symbols(geometry(A, q_m, rate) // q_m) + rx_stream.TAPS - 1


def amplitude(burst, snr_db):
    """Scale for Es/N0 = snr_db against the fixed noise floor (SPS samples per symbol)."""
    return NOISE_RMS * np.sqrt(10 ** (snr_db / 10) / rx_phy.SPS / np.mean(np.abs(burst) ** 2))


def adc(x, rng):
    """Add the noise floor, round and saturate to 12-bit codes."""
    x = x + NOISE_RMS / np.sqrt(2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    clip = lambda v: np.clip(np.round(v), -rx_phy.ADC_MAX - 1, rx_phy.ADC_MAX)
    return clip(x.real) + 1j * clip(x.imag)


def stream(transports, rng, multiple=1):
    """Lay out bursts back to back after their gaps.

    Each transport is a dict with payload, Q_m, G and snr_db, and optionally
    gap (samples, default MIN_GAP), cfo (fraction of the receiver's range,
    default uniform in +-0.75), fraction (sample delay in [0, 1), default
    uniform) and phase (radians, default uniform). MIN_GAP idle samples follow
    the last burst, then noise up to a multiple of `multiple` samples.
    Returns the ADC samples and each burst's first sample.
    """
    pieces, starts, position = [], [], 0
    for t in transports:
        gap = int(t.get("gap", MIN_GAP))
        pieces.append(np.zeros(gap, dtype=complex))
        position += gap
        burst = rx_stream.modulate(t["payload"], t["Q_m"], t["G"], t.get("fraction", rng.random()))
        cfo = t.get("cfo", rng.uniform(-.75, .75)) * CFO_RANGE
        phase = t.get("phase", rng.uniform(0, 2 * np.pi))
        n = np.arange(len(burst))
        pieces.append(burst * amplitude(burst, t["snr_db"]) * np.exp(1j * (phase + cfo / rx_phy.SPS * n)))
        starts.append(position)
        position += len(burst)
    pieces.append(np.zeros(-(position + MIN_GAP) % multiple + MIN_GAP, dtype=complex))
    return adc(np.concatenate(pieces), rng), starts
