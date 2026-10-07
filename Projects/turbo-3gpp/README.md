# LTE turbo receiver on a continuous ADC stream

`main.py` is the `convert.py` / `sim.py` target. It models what a Pluto
(AD9363) receiver sees: an endless stream of 12-bit complex ADC samples in
which bursts arrive at arbitrary times, separated by idle noise. Each burst
announces its own length, modulation and coded size in an in-band header, so
the receiver needs no side information. `rx_stream.py` detects bursts, syncs,
decodes the header and decodes the data with the existing `python/turbo_3gpp`
chain (algorithms unchanged). It does not implement LTE OFDM, multipath
equalization, sample-clock tracking, HARQ or 5G NR channel coding.

From the repository root:

```sh
python3 Projects/turbo-3gpp/main.py                  # reference BER per noise level
python3 sim.py -p Projects/turbo-3gpp                # write input/output streams only
python3 Projects/turbo-3gpp/rx_smoke.py --suite quick --octave
python3 convert.py -m codex -i Projects/turbo-3gpp
```

NumPy and PyYAML are required; `--octave` also needs SciPy and Octave.

## Stimulus

`generate(samples)` builds one continuous ADC stream from random bursts. Each
burst draws every parameter independently (unseeded):
- payload length A, log-uniform from 16 up to the largest that fits `max_burst`
  (at most 16384);
- Q_m: QPSK, 16QAM, 64QAM or 256QAM;
- nominal code rate: 1/3, 1/2, 2/3, 3/4 or 5/6;
- noise level: the Es/N0 where this receiver's decoded BER is 1e-1, 1e-2 or 1e-3
  for that Q_m and rate (table in `main.py`, measured once with A=2048), or a
  clean level 10 dB above the 1e-3 point;
- CFO (+-95% of the receiver's range), fractional delay, carrier phase, and an
  idle gap of 32 to 288 samples.

Bursts fill about 93% of the samples. The fixed noise floor is 16 codes RMS;
samples are rounded and saturated to 12 bits. Generation continues one
`max_burst` past the requested samples, so output that has already started can
finish. `sim_samples` (163840) is the default measured length, about 5 s of
Python.

`python3 main.py` instead streams for `time_budget_s` (60 s, a hard stop) and
prints the reference receiver against the transmitted bits for each level:
bursts sent, missed (no packet reported), CRC accepted, and decoded BER over
the received packets. A level's BER should come out near its nominal value;
differences come from block length (A varies here) and run size. If it is far
worse, the receiver is suboptimal at that point. This is how the two-pilot
phase tracking from `rx_phy.py` was found to cost about 1.5 dB.

## Stream contract

`params.yaml`: input scalars are signed 12-bit, FRAC 0, two per sample (I then
Q); output scalars are unsigned 1-bit. `target.sample_rate` is 10 MS/s at
`target.frequency` 100 MHz, so 10 clock cycles per ADC sample, a typical Pluto
rate. `max_burst` is 8192 samples. The receiver settings are `iterations_x2`=8
(4 turbo iterations) and `approximate`=1 (max-log).

Input: the ADC stream, with no padding and no side channel. The receiver keeps
state for the whole stream and resets only with hardware reset.

Output: a bit stream. For each packet, in order of completion: a 33-bit
descriptor, most significant bit first, then the A payload hard decisions.

| Field | Bits | Meaning |
| --- | --- | --- |
| crc | 1 | CRC accepted |
| length | 14 | A - 1 |
| modulation | 2 | Q_m index into (2, 4, 6, 8) |
| symbols | 16 | S data symbols |

Payload hard decisions are output even when CRC rejects the packet. A burst
whose header fails is not reported. Every bit is determined once the packet's
last used sample has arrived (`ready`). How many bits travel per AXI beat is
the RTL's choice (`OUT_LANES`). The stream averages about 0.64 output bits per
input sample, but a 256QAM rate-5/6 burst produces about 3.3, so a narrow output
needs buffering. There is no padding.

## Air interface

`rx_stream.py`'s docstring defines the burst and the receiver exactly. In brief,
at 2 samples per symbol with root-raised-cosine pulses (rolloff 0.35, 8-symbol
span, receive taps quantized to 2^-15):

- Preamble: 128 QPSK symbols, eight 16-symbol Frank segments, cover
  `+ + + + - + + -`.
- Header: 32 bits (A-1: 14 bits, Q_m index: 2 bits, S: 16 bits) through the
  unchanged LTE turbo chain (CRC24A, K=56), rate-matched to 384 BPSK symbols.
- Data: S = G/Q_m symbols, LTE 36.211 Gray mapping; G divisible by C*Q_m.
- Pilots (1+j)/sqrt(2) before every 32 symbols of header+data and one after.
- Detection: power-normalized differential preamble metric M(d) >= 0.2. On
  noise, M stayed below 0.17 in 4M samples. At Es/N0 -3 dB the peak is
  0.16-0.3, so there are occasional misses at the lowest QPSK points.
- Sync as in `rx_phy.py`: coarse CFO and timing from the preamble, fine timing
  to 1/32 sample, channel and noise from the preamble. Phase is tracked over a
  window of 8 pilots around each block, clipped at the ends of the burst.
- LLRs: max-log, scaled by |h|^2/noise, rounded to 1/16 and clipped to +-16.
- A failed header resumes the search 32 samples after the coarse peak. A decoded
  packet resumes the search after its last symbol.

Not modeled: multipath, sample-clock offset, I/Q imbalance, DC offset, phase
noise and overlapping bursts.

## Measurement

Output is compared with the reference receiver, not with the transmitted bits.
`generate` defines disjoint measurement groups over the output bits: payload,
crc, length, modulation and symbols. Each group reports its own mismatches,
RMSE and precision log2(peak/RMSE); for bits, precision is -0.5 log2(mismatch
rate). There is no combined score or cutoff. Cycles/sample against
`target.sample_rate` shows whether the design keeps up with the ADC.

## Codec coverage

`rx_smoke.py` is the earlier windowed, single-burst interface. It has a
per-window control lane, HARQ with eight processes, and the old two-pilot
`rx_phy.py` front end. It remains a Python coverage test of the codec: all 188
QPP sizes, segmentation and filler boundaries, every redundancy version with
each modulation order and 1/2/4 layers, limited buffers, exact/max-log decoding,
iteration limits and HARQ combining. `--octave` compares each transaction's
decoder against the original MATLAB chain. Its payloads and noise are
controlled by `--seed` (default 20260928). It is not streamed to RTL.
