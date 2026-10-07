"""Continuous-stream burst PHY: an endless ADC sample stream in, packets out.

The Pluto ADC never stops; bursts arrive whenever the transmitter sends them,
at arbitrary sample offsets, separated by idle gaps of noise. Each burst
describes itself with an in-band header, so the receiver needs no side
information. Everything here is the oracle RTL must reproduce.

Burst, at SPS samples per symbol (pulse shaping, preamble, pilots and LTE
Gray mapping as in rx_phy.py):
    preamble  128 QPSK symbols (8 x 16-symbol Frank segments, Barker cover)
    header    HEADER_G BPSK symbols: 32 header bits through the unchanged LTE
              turbo chain (CRC24A, K=56, rate matching to HEADER_G, rv 0)
    data      S = G/Q_m symbols carrying the turbo-coded payload (rv 0)
    pilots    one before every BLOCK symbols of header+data and one after the
              last, laid out over header and data as one sequence. The header
              is exactly 12 blocks, so its last pilot is the first data pilot.
Header bits, MSB first: A-1 (14 bits), Q_m index into MODULATIONS (2 bits),
S (16 bits). A transmitter chooses G = S*Q_m divisible by C*Q_m.

Receiver, from search position p (0 at reset):
    1. y = matched filter of x (17-tap RRC, valid); c(d) segment correlations,
       D(d) the differential metric of rx_phy.py; P(d) = sum |y[d+i]|^2 for
       i < 255 (the preamble span). M(d) = |D(d)| / (7 P(d)), 0 if P(d) = 0.
       M is about 1 for a clean preamble, below 0.17 for noise.
    2. Detection: the first d >= p with M(d) >= THRESHOLD. t0 = d + first
       argmax |D| over [d, d + PEAK), PEAK = 256 samples (one preamble): with
       a few segments of overlap M already crosses THRESHOLD up to 7 segments
       early, and the full-overlap peak is the largest. CFO w = angle(D(t0)) / 16
       per symbol. c(d) here sums y[d+2i] conj(SEGMENT[i]) in order i = 0..15.
    3. Derotate x'[n] = x[n] exp(-j w (n - t0) / SPS); fine timing, fraction,
       symbol-rate matched filter, channel, noise and LLRs exactly as
       rx_phy.demodulate steps 4, 5 and 7, with the fine search over
       [t0-3, t0+3] clipped at sample 0. Phase tracking replaces step 6:
       q_k = z[pilot_k] conj(h PILOT); block b (between pilots b and b+1) is
       rotated by the unit phasor of sum q_k for k in [b-TRACK+1, b+TRACK],
       clipped to existing pilots (1 if the sum is zero). rx_phy's two-pilot
       average cost about 1.5 dB at low Es/N0.
    4. Decode the header (HEADER_ITERATIONS_X2, max-log). If its CRC fails or
       its fields are invalid (S = 0, burst over MAX_BURST samples, or the
       rate-matching segment lengths do not sum to G), resume at p = t0 + PEAK.
    5. Otherwise decode the data and resume at p = base + SPS * symbols, the
       first sample after the burst's symbol grid.
A packet is complete once the receiver has every sample it used:
last = base + SPS * (symbols - 1) + 17. It is reported in the frame that
contains sample `last`.
"""
import numpy as np
from turbo_3gpp import core, turbo_decoding_chain, turbo_encoding_chain
from turbo_3gpp.core import calculate_crc_bits, turbo_decoder
import rx_phy
from rx_phy import BLOCK, PHASES, PILOT, PREAMBLE, RRC, SEGMENT, SPS

MODULATIONS = (2, 4, 6, 8)
HEADER_BITS = 32
HEADER_G = 384
HEADER_ITERATIONS_X2 = 8
THRESHOLD = 0.2
PEAK = len(PREAMBLE) * SPS                    # a partial preamble overlap also crosses THRESHOLD
TRACK = 4                                     # pilots each side of a block for phase
SPAN = len(SEGMENT) * SPS                     # 32 samples per preamble segment
REACH = SPAN * (len(rx_phy.COVER) - 1) + SPS * (len(SEGMENT) - 1) + len(RRC) - 1
TAPS = PHASES.shape[1]
HEADER_REGION = len(PREAMBLE) + (HEADER_G // BLOCK) * (BLOCK + 1) + 1


def header_bits(A, q_m, S):
    value = ((A - 1) << 18) | (MODULATIONS.index(q_m) << 16) | S
    return (value >> np.arange(HEADER_BITS - 1, -1, -1)) & 1


def header_fields(bits):
    value = int(np.asarray(bits, dtype=int) @ (1 << np.arange(HEADER_BITS - 1, -1, -1)))
    return (value >> 18) + 1, MODULATIONS[(value >> 16) & 3], value & 0xFFFF


def burst_symbols(S):
    return len(PREAMBLE) + HEADER_G + S + -(-(HEADER_G + S) // BLOCK) + 1


def valid_geometry(A, G, q_m, max_burst):
    """The transmitter's constraints, which the receiver also checks."""
    C = len(core.get_3gpp_code_block_segment_lengths(A + 24))
    E = core.get_3gpp_encoded_code_block_segment_lengths(G, C, 1, q_m)
    return G > 0 and G % q_m == 0 and sum(E) == G and SPS * burst_symbols(G // q_m) + TAPS <= max_burst


def modulate(payload, q_m, G, fraction=0.0):
    """Payload bits -> one baseband burst (unit symbol energy), delayed by fraction."""
    A = len(payload)
    header = chain("encode", HEADER_BITS, HEADER_G, 1)(header_bits(A, q_m, G // q_m))
    data = chain("encode", A, G, q_m)(np.asarray(payload, dtype=int))
    stream = np.zeros(burst_symbols(G // q_m), dtype=complex)
    positions, pilots = rx_phy.layout(HEADER_G + G // q_m)
    stream[:len(PREAMBLE)] = PREAMBLE
    stream[pilots] = PILOT
    stream[positions[:HEADER_G]] = rx_phy.constellation(1)[header.astype(int)]
    labels = data.astype(int).reshape(-1, q_m) @ (1 << np.arange(q_m - 1, -1, -1))
    stream[positions[HEADER_G:]] = rx_phy.constellation(q_m)[labels]
    upsampled = np.zeros(len(stream) * SPS, dtype=complex)
    upsampled[::SPS] = stream
    pulse = rx_phy._pulse((np.arange(TAPS) - (TAPS - 2) / 2 - fraction) / SPS) / rx_phy._NORM
    return np.convolve(upsampled, pulse)


def _metric(y, count):
    """Differential preamble metric D(d) for d in [0, count) of filtered y."""
    n = count + SPAN * (len(rx_phy.COVER) - 1)
    c = np.zeros(n, dtype=complex)
    for i, s in enumerate(np.conj(SEGMENT)):
        c += y[SPS * i:SPS * i + n] * s
    D = np.zeros(count, dtype=complex)
    for k, e in enumerate(rx_phy.DIFFERENTIAL):
        D += e * c[SPAN * (k + 1):SPAN * (k + 1) + count] * np.conj(c[SPAN * k:SPAN * k + count])
    return D


def _metrics(x, start, count):
    """D(d) and M(d) for d in [start, start + count); needs x[:start+count+REACH]."""
    y = np.convolve(x[start:start + count + REACH], RRC, mode="valid")
    D = _metric(y, count)
    power = np.concatenate([[0], np.cumsum(np.abs(y) ** 2)])
    P = power[SPAN * (len(rx_phy.COVER) - 1) + SPS * (len(SEGMENT) - 1) + 1:][:count] - power[:count]
    return D, np.where(P > 0, np.abs(D) / (7 * np.where(P > 0, P, 1)), 0)


_chains = {}


def chain(kind, A, G, q_m, iterations_x2=0):
    """A set-up coding chain, cached: setup (CRC matrices, interleavers) dominates small packets."""
    key = (kind, A, G, q_m, iterations_x2)
    if key in _chains:
        _chains[key] = _chains.pop(key)          # most recently used last
    else:
        if len(_chains) >= 8:
            del _chains[next(iter(_chains))]
        if kind == "encode":
            _chains[key] = turbo_encoding_chain(A=A, G=G, Q_m=q_m)
        else:
            _chains[key] = turbo_decoding_chain(A=A, G=G, Q_m=q_m, iterations=iterations_x2 / 2)
        _chains[key].setupImpl()
        _chains[key]._ready = True
    return _chains[key]


def _hard_decode(A, G, q_m, llrs, iterations_x2, approximate):
    """The unchanged decoding chain, keeping hard decisions when CRC fails.

    Returns (payload hard decisions, CRC accepted). When accepted, the bits
    equal what turbo_decoding_chain returns.
    """
    chain_ = chain("decode", A, G, q_m, iterations_x2)
    previous = core.approx_star
    core.approx_star = bool(approximate)
    try:
        blocks, accepted = [], True
        crc = chain_.CRC_generator_matrix_CB if chain_.C > 1 else chain_.CRC_generator_matrix_TB
        for r, e in enumerate(core.code_block_deconcatenation(llrs, chain_.E_r)):
            v = np.zeros(3 * chain_.D_r[r])
            np.add.at(v, chain_.rate_matching_patterns[r], e)
            d = v.reshape(3, chain_.D_r[r], order='F')
            d[:2, :chain_.F_r[r]] = np.nan
            c, _ = turbo_decoder(d, chain_.internal_interleaver_patterns[r], chain_.iterations, crc)
            c = np.asarray(c)
            if chain_.C > 1:
                accepted &= np.array_equal(c[-chain_.L_CB:], calculate_crc_bits(np.nan_to_num(c[:-chain_.L_CB]), crc))
                c = c[:-chain_.L_CB]
            blocks.append(c[chain_.F_r[r] if r == 0 else 0:])
    finally:
        core.approx_star = previous
    b = np.concatenate(blocks)
    payload = b[:A]
    accepted &= np.array_equal(b[A:A + 24], calculate_crc_bits(payload, chain_.CRC_generator_matrix_TB))
    return payload.astype(int), bool(accepted)


class Sync:
    """Steps 3 of the receiver: timing, CFO, channel and noise for one detection."""

    def __init__(self, x, d, D):
        t0 = d + int(np.argmax(np.abs(D)))
        self.t0 = t0
        self.w = np.angle(D[t0 - d]) / len(SEGMENT)
        first, last = max(t0 - rx_phy.REFINE - 1, 0), t0 + rx_phy.REFINE + 1
        fine = _metric(np.convolve(self.derotate(x, first, last + 1 + REACH), RRC, mode="valid"),
                       last + 1 - first)
        low = max(t0 - rx_phy.REFINE, 0)
        peak = low + int(np.argmax(np.abs(fine[low - first:t0 + rx_phy.REFINE + 1 - first])))
        mu = 0.0
        if first < peak < last:
            a, b, c = np.abs(fine[peak - first - 1:peak - first + 2]) ** 0.25
            if a - 2 * b + c < 0:
                mu = float(np.clip(0.5 * (a - c) / (a - 2 * b + c), -0.5, 0.5))
        self.base = int(np.floor(peak + mu))
        self.phase = int(np.round((peak + mu - self.base) * rx_phy.FRACTION_STEPS))
        if self.phase == rx_phy.FRACTION_STEPS:
            self.base, self.phase = self.base + 1, 0
        preamble = self.symbols(x, 0, len(PREAMBLE))
        self.h = np.mean(preamble * np.conj(PREAMBLE))
        self.var = max(np.mean(np.abs(preamble - self.h * PREAMBLE) ** 2),
                       abs(self.h) ** 2 / rx_phy.NOISE_FLOOR)

    def derotate(self, x, start, stop):
        n = np.arange(start, stop)
        return x[start:stop] * np.exp(-1j * self.w / SPS * (n - self.t0))

    def end(self, symbols):
        """One past the last sample that the first `symbols` symbols use."""
        return self.base + SPS * (symbols - 1) + TAPS

    def symbols(self, x, first, count):
        start = self.base + SPS * first
        window = self.derotate(x, start, start + SPS * (count - 1) + TAPS)
        index = SPS * np.arange(count)[:, None] + np.arange(TAPS)[None, :]
        return window[index] @ PHASES[self.phase]

    def llrs(self, x, sequence, first, count, q_m):
        """LLRs of header+data symbols [first, first+count) of a `sequence`-symbol body."""
        data, pilots = rx_phy.layout(sequence)
        z = self.symbols(x, 0, pilots[-1] + 1)
        if self.h == 0:
            return np.zeros(count * q_m)
        q = np.concatenate([[0], np.cumsum(z[pilots] * np.conj(self.h * PILOT))])
        # Block b sits between pilots b and b+1; average pilots b-TRACK+1..b+TRACK.
        b = np.arange(len(pilots) - 1)
        total = q[np.minimum(b + TRACK + 1, len(pilots))] - q[np.maximum(b - TRACK + 1, 0)]
        rotation = np.where(total == 0, 1, total / np.where(total == 0, 1, np.abs(total)))
        index = np.arange(first, first + count)
        s = z[data[index]] * np.conj(rotation[index // BLOCK]) / self.h
        llrs = rx_phy._llrs(s, q_m, abs(self.h) ** 2 / self.var)
        return np.clip(np.round(llrs / rx_phy.LLR_STEP) * rx_phy.LLR_STEP, -rx_phy.LLR_MAX, rx_phy.LLR_MAX)


class StreamReceiver:
    """Feed consecutive sample blocks; returns packets as they complete."""

    def __init__(self, iterations_x2, approximate, max_burst):
        self.iterations_x2, self.approximate, self.max_burst = iterations_x2, approximate, max_burst
        self.x = np.zeros(0, dtype=complex)
        self.p = 0
        self.pending = None          # (Sync, A, q_m, S) once a header decodes

    def push(self, samples):
        self.x = np.concatenate([self.x, np.asarray(samples, dtype=complex)])
        packets = []
        while True:
            if self.pending is None:
                found = self._detect()
                if found is None:
                    return packets
                sync = Sync(self.x, *found)
                if sync.end(HEADER_REGION) > len(self.x):
                    return packets                # p stays at d; redone with more samples
                header, ok = _hard_decode(HEADER_BITS, HEADER_G, 1,
                                          sync.llrs(self.x, HEADER_G, 0, HEADER_G, 1),
                                          HEADER_ITERATIONS_X2, 1)
                A, q_m, S = header_fields(header)
                if not ok or not S or not valid_geometry(A, S * q_m, q_m, self.max_burst):
                    self.p = sync.t0 + PEAK
                    continue
                self.pending = (sync, A, q_m, S)
            sync, A, q_m, S = self.pending
            symbols = burst_symbols(S)
            if sync.end(symbols) > len(self.x):
                return packets
            llrs = sync.llrs(self.x, HEADER_G + S, HEADER_G, S, q_m)
            payload, accepted = _hard_decode(A, S * q_m, q_m, llrs, self.iterations_x2, self.approximate)
            packets.append(dict(A=A, Q_m=q_m, S=S, crc=accepted, payload=payload,
                                start=sync.base, last=sync.end(symbols) - 1))
            self.p = sync.base + SPS * symbols
            self.pending = None

    def _detect(self):
        """(d, D over [d, d+PEAK)) for the next detection with its samples present, else None."""
        while True:
            count = len(self.x) - REACH - self.p
            if count <= 0:
                return None
            D, M = _metrics(self.x, self.p, min(count, 1 << 15))
            hits = np.flatnonzero(M >= THRESHOLD)
            if not len(hits):
                self.p += len(M)
                continue
            d = self.p + int(hits[0])
            if d + PEAK + REACH > len(self.x):
                self.p = d                       # wait for the rest of the peak window
                return None
            D, _ = _metrics(self.x, d, PEAK)
            # Fine timing reads up to t0 + REFINE + 1 + REACH.
            if d + PEAK + rx_phy.REFINE + 1 + REACH > len(self.x):
                self.p = d
                return None
            self.p = d
            return d, D
