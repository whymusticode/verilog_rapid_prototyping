"""Floating-point reference model for the Pluto dual-RX analysis PFB.

The model uses the conventional critically sampled analysis-bank layout:
one ``channels``-sample input frame produces one FFT frame.  ``process`` is
stateful, so it is suitable for a streaming Python test as well as the
single-frame ``target`` wrapper used by verilog_rapid_prototyping.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def bit_reverse_indices(channels: int) -> np.ndarray:
    """Return the output permutation used by the existing FFT project."""
    if channels <= 0 or channels & (channels - 1):
        raise ValueError("channels must be a positive power of two")
    bits = channels.bit_length() - 1
    indices = np.arange(channels, dtype=np.uint32)
    reversed_indices = np.zeros_like(indices)
    for bit in range(bits):
        reversed_indices = (reversed_indices << 1) | ((indices >> bit) & 1)
    return reversed_indices


def prototype_taps(channels: int, taps_per_phase: int, beta: float) -> np.ndarray:
    """Design a real, windowed-sinc prototype and return [tap, phase] taps.

    Cutoff is one half channel spacing.  The resulting matrix is arranged so
    ``taps[t, phase]`` multiplies the sample delayed by ``t`` PFB frames.
    """
    length = channels * taps_per_phase
    sample = np.arange(length, dtype=float) - (length - 1) / 2
    cutoff = 1.0 / (2.0 * channels)  # cycles per input sample
    impulse = 2.0 * cutoff * np.sinc(2.0 * cutoff * sample)
    impulse *= np.kaiser(length, beta)
    impulse /= np.sum(impulse)
    return impulse.reshape(taps_per_phase, channels)


def quantize_coefficients(taps: np.ndarray, bits: int) -> np.ndarray:
    """Return signed fixed-point Q1.(bits-1) coefficient integers."""
    if bits < 2:
        raise ValueError("coefficient width must be at least two bits")
    scale = (1 << (bits - 1)) - 1
    return np.rint(np.asarray(taps) * scale).astype(np.int64)


@dataclass
class PolyphaseChannelizer:
    channels: int
    taps_per_phase: int
    beta: float
    coefficients: np.ndarray = field(init=False)
    _history: np.ndarray | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.coefficients = prototype_taps(
            self.channels, self.taps_per_phase, self.beta
        )

    def reset(self) -> None:
        self._history = None

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Channelize ``[channels, rx_count]`` complex input samples.

        The returned shape is ``[channels, rx_count]``.  Frames are ordered
        oldest-to-newest internally; a new instance therefore models the
        hardware reset condition with zero pre-history.
        """
        frame = np.asarray(frame, dtype=np.complex128)
        if frame.ndim != 2 or frame.shape[0] != self.channels:
            raise ValueError(
                f"frame must have shape ({self.channels}, rx_count), got {frame.shape}"
            )
        rx_count = frame.shape[1]
        if self._history is None:
            self._history = np.zeros(
                (self.taps_per_phase - 1, self.channels, rx_count), dtype=np.complex128
            )
        elif self._history.shape[2] != rx_count:
            raise ValueError("rx_count changed without resetting channelizer")

        windows = np.concatenate((self._history, frame[None, :, :]), axis=0)
        branches = np.einsum("tp,tpr->pr", self.coefficients, windows)
        self._history = windows[1:].copy()
        spectrum = np.fft.fft(branches, axis=0)
        # This is the fixed hardware interface contract.  A streaming
        # radix-2 FFT naturally emits bit-reversed bins; reordering belongs
        # downstream if a consumer needs natural bin numbering.
        return spectrum[bit_reverse_indices(self.channels)]
