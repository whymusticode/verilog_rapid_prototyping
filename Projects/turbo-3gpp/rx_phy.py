"""Single-carrier burst PHY: raw ADC IQ in, rate-matched LLRs out.

This is the air interface in front of the turbo receiver. One harness frame is
a window of N complex ADC samples (12-bit codes, as the Pluto AD9363 delivers
them) that contains one burst at an unknown position, with unknown carrier
frequency offset, phase, gain and fractional delay. The receiver below is the
oracle: every step is defined here so RTL can reproduce it.

Burst, at SPS samples per symbol with root-raised-cosine pulses:
    preamble  8 x 16-symbol Frank segment, segment k multiplied by COVER[k]
    data      G/Q_m symbols (LTE 36.211 Gray mapping), a pilot before every
              block of BLOCK data symbols and one after the last block
Receiver:
    1. matched filter y = RRC (valid convolution; 17 taps quantized to 2^-15)
    2. segment correlations c(d) = sum_i y[d + SPS*i] conj(SEGMENT[i]), i<16
    3. differential metric D(d) = sum_k e_k c(d+32(k+1)) conj(c(d+32k)),
       e_k = COVER[k] COVER[k+1] (Barker 7); t0 = first argmax |D(d)|
       over d < SEARCH; CFO per symbol w = angle(D(t0)) / 16
    4. derotate the raw samples, x'[n] = x[n] exp(-j w n / SPS), and repeat
       steps 1-3 on x' for d in [t0-3, t0+3] (clipped to the window). CFO
       skews the peak of the rotated metric; derotated, it is unbiased.
       t = first argmax |D'(d)| over [t0-2, t0+2]; a parabola through
       |D'|^(1/4) at t-1, t, t+1 gives mu in [-1/2, 1/2] (0 if not concave
       or at the window edge); t + mu = base + f with f rounded to 1/32. Symbols come from
       matched-filtering x' at symbol rate with the 18-tap RRC phase for f
       (PHASES[f], taps quantized 2^-15):
       z[i] = sum_j PHASES[f][j] x'[base + SPS*i + j]
    5. flat channel h = mean z conj(P) over the preamble; noise
       var = max(mean |z - hP|^2, |h|^2 / NOISE_FLOOR)
    6. pilot correlations q_b = z[pilot_b] conj(h PILOT); block b is rotated
       by u_b = (q_b + q_b+1)/|q_b + q_b+1| (1 if zero); s = z conj(u_b) / h
    7. max-log LLR per bit, positive favoring 0, scaled by |h|^2/var, rounded
       to 1/16 and clipped to +-16 (the turbo decoder's input format)
"""
import numpy as np

SPS = 2
BETA = 0.35
SPAN = 8                    # symbols; 2*SPS*... gives SPAN*SPS+1 taps
BLOCK = 32                  # data symbols between pilots
SEARCH = 1024               # timing search window in samples
REFINE = 2                  # samples searched around the coarse peak after derotation
FRACTION_STEPS = 32        # matched-filter phases per sample
NOISE_FLOOR = 1e4           # caps the SNR the LLR scaling assumes (40 dB)
LLR_STEP, LLR_MAX = 1 / 16, 16
ADC_MAX = 2047

# Frank sequence (L=4): perfect periodic autocorrelation, QPSK after 45 degrees.
SEGMENT = np.exp(1j * (np.pi / 4 + 2 * np.pi / 4 * np.outer(np.arange(4), np.arange(4)).ravel()))
COVER = np.array([1, 1, 1, 1, -1, 1, 1, -1])
DIFFERENTIAL = COVER[:-1] * COVER[1:]            # Barker 7: + + + - - + -
PREAMBLE = np.concatenate([cover * SEGMENT for cover in COVER])
PILOT = (1 + 1j) / np.sqrt(2)


def _pulse(t):
    """Root-raised-cosine at t symbols, zero outside the SPAN truncation."""
    h = np.zeros_like(t)
    for index, x in enumerate(t):
        if abs(x) > SPAN / 2 + 1e-12:
            continue
        if x == 0:
            h[index] = 1 - BETA + 4 * BETA / np.pi
        elif abs(abs(4 * BETA * x) - 1) < 1e-12:
            h[index] = BETA / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * BETA))
                                            + (1 - 2 / np.pi) * np.cos(np.pi / (4 * BETA)))
        else:
            h[index] = (np.sin(np.pi * x * (1 - BETA)) + 4 * BETA * x * np.cos(np.pi * x * (1 + BETA))) \
                / (np.pi * x * (1 - (4 * BETA * x) ** 2))
    return h


_NORM = np.sqrt(np.sum(_pulse((np.arange(SPAN * SPS + 1) - SPAN * SPS / 2) / SPS) ** 2))
RRC = np.round(_pulse((np.arange(SPAN * SPS + 1) - SPAN * SPS / 2) / SPS) / _NORM * 2 ** 15) / 2 ** 15
# PHASES[k][j] filters x[n + j] to the matched-filter output at n + k/16.
PHASES = np.array([np.round(_pulse((k / FRACTION_STEPS + SPAN * SPS / 2 - np.arange(SPAN * SPS + 2)) / SPS)
                            / _NORM * 2 ** 15) / 2 ** 15 for k in range(FRACTION_STEPS)])


def _levels(m):
    """Per-axis LTE Gray PAM: amplitude for each m-bit label (MSB = sign bit)."""
    labels = np.arange(1 << m)
    bits = (labels[:, None] >> (m - 1 - np.arange(m))) & 1
    value = np.ones(len(labels))
    for position in range(m - 1, 0, -1):
        value = (1 << (m - position)) - (1 - 2 * bits[:, position]) * value
    return (1 - 2 * bits[:, 0]) * value, bits


def constellation(q_m):
    """Unit-average-energy LTE points for q_m bits (b0 first), 36.211 7.1."""
    if q_m == 1:
        return np.array([1, -1]) * PILOT
    m = q_m // 2
    amplitude, _ = _levels(m)
    scale = np.sqrt(2 * np.mean(amplitude ** 2))
    labels = np.arange(1 << q_m)
    bits = (labels[:, None] >> (q_m - 1 - np.arange(q_m))) & 1
    index_i = bits[:, 0::2] @ (1 << np.arange(m - 1, -1, -1))
    index_q = bits[:, 1::2] @ (1 << np.arange(m - 1, -1, -1))
    return (amplitude[index_i] + 1j * amplitude[index_q]) / scale


def layout(symbols):
    """Symbol indices of pilots and data after the preamble."""
    blocks = -(-symbols // BLOCK)
    data = len(PREAMBLE) + (np.arange(symbols) // BLOCK) * (BLOCK + 1) + 1 + np.arange(symbols) % BLOCK
    # One pilot before each block, and one right after the last data symbol.
    pilots = len(PREAMBLE) + np.append(np.arange(blocks) * (BLOCK + 1), blocks + symbols)
    return data, pilots


def burst_symbols(G, q_m):
    return len(PREAMBLE) + G // q_m + -(-(G // q_m) // BLOCK) + 1


def modulate(bits, q_m, fraction=0.0):
    """Rate-matched bits -> baseband burst samples (unit symbol energy).

    ``fraction`` delays the pulses by that many samples, as an unsynchronized
    transmitter clock would; the TX pulse is the unquantized RRC.
    """
    bits = np.asarray(bits, dtype=int)
    symbols = len(bits) // q_m
    data, pilots = layout(symbols)
    stream = np.zeros(burst_symbols(len(bits), q_m), dtype=complex)
    stream[:len(PREAMBLE)] = PREAMBLE
    stream[pilots] = PILOT
    if symbols:
        labels = bits.reshape(symbols, q_m) @ (1 << np.arange(q_m - 1, -1, -1))
        stream[data] = constellation(q_m)[labels]
    upsampled = np.zeros(len(stream) * SPS, dtype=complex)
    upsampled[::SPS] = stream
    pulse = _pulse((np.arange(SPAN * SPS + 2) - SPAN * SPS / 2 - fraction) / SPS) / _NORM
    return np.convolve(upsampled, pulse)


def _llrs(s, q_m, scale):
    if q_m == 1:
        return scale * 4 * np.real(s * np.conj(PILOT))
    m = q_m // 2
    amplitude, bits = _levels(m)
    amplitude = amplitude / np.sqrt(2 * np.mean(amplitude ** 2))
    result = np.empty((len(s), q_m))
    for axis, values in enumerate((s.real, s.imag)):
        distance = (values[:, None] - amplitude[None, :]) ** 2
        for bit in range(m):
            one = bits[:, bit] == 1
            result[:, axis + 2 * bit] = scale * (distance[:, one].min(1) - distance[:, ~one].min(1))
    return result.ravel()


def _metric(y, start, count):
    """Differential preamble metric D(d) for d in [start, start + count)."""
    span = len(SEGMENT) * SPS
    c = np.array([np.dot(y[d:d + span:SPS], np.conj(SEGMENT))
                  for d in range(start, start + count + span * (len(COVER) - 1))])
    return sum(e * c[span * (k + 1):span * (k + 1) + count] * np.conj(c[span * k:span * k + count])
               for k, e in enumerate(DIFFERENTIAL))


def demodulate(iq, G, q_m):
    """ADC samples (complex, length N) -> quantized LLRs for G bits."""
    symbols = G // q_m
    total = burst_symbols(G, q_m)
    coarse = _metric(np.convolve(iq, RRC, mode="valid"), 0, SEARCH)
    timing = int(np.argmax(np.abs(coarse)))
    w = np.angle(coarse[timing]) / len(SEGMENT)
    # CFO rotation skews the metric's peak; locate it again once derotated.
    derotated = iq * np.exp(-1j * w / SPS * np.arange(len(iq)))
    first, last = max(timing - REFINE - 1, 0), min(timing + REFINE + 1, SEARCH - 1)
    fine = _metric(np.convolve(derotated, RRC, mode="valid"), first, last + 1 - first)
    low, high = max(timing - REFINE, 0), min(timing + REFINE, SEARCH - 1)
    peak = low + int(np.argmax(np.abs(fine[low - first:high + 1 - first])))
    mu = 0.0
    if first < peak < last:
        # |D| goes as |c|^2; its fourth root has the most parabolic peak.
        a, b, c = np.abs(fine[peak - first - 1:peak - first + 2]) ** 0.25
        if a - 2 * b + c < 0:
            mu = float(np.clip(0.5 * (a - c) / (a - 2 * b + c), -0.5, 0.5))
    base = int(np.floor(peak + mu))
    phase = int(np.round((peak + mu - base) * FRACTION_STEPS))
    if phase == FRACTION_STEPS:
        base, phase = base + 1, 0
    derotated = np.concatenate([derotated, np.zeros(SPAN * SPS + 2)])
    taps = PHASES[phase]
    windows = base + SPS * np.arange(total)[:, None] + np.arange(len(taps))[None, :]
    z = derotated[windows] @ taps
    preamble = z[:len(PREAMBLE)]
    h = np.mean(preamble * np.conj(PREAMBLE))
    if h == 0:
        return np.zeros(G)
    var = max(np.mean(np.abs(preamble - h * PREAMBLE) ** 2), abs(h) ** 2 / NOISE_FLOOR)
    data, pilots = layout(symbols)
    q = z[pilots] * np.conj(h * PILOT)
    pair = q[:-1] + q[1:]
    rotation = np.where(pair == 0, 1, pair / np.where(pair == 0, 1, np.abs(pair)))
    s = z[data] * np.conj(rotation[np.arange(symbols) // BLOCK]) / h
    llrs = _llrs(s, q_m, abs(h) ** 2 / var)
    return np.clip(np.round(llrs / LLR_STEP) * LLR_STEP, -LLR_MAX, LLR_MAX)


def transmit(bits, q_m, n, rng, snr_db, rms=None, cfo=None):
    """One burst received in an n-sample ADC window with realistic impairments.

    The burst starts at a random sample in [4, SEARCH - 64) plus a random
    fraction, with random phase, CFO (radians per symbol), gain set by the
    burst RMS in ADC codes, and complex AWGN at Es/N0 = snr_db; samples are
    then rounded to integers and saturated to 12 bits.
    """
    rms = rng.uniform(150, 700) if rms is None else rms
    cfo = rng.uniform(-.75, .75) * np.pi / len(SEGMENT) if cfo is None else cfo
    delay = int(rng.integers(4, SEARCH - 64))
    burst = modulate(bits, q_m, rng.random())
    if delay + len(burst) > n:
        raise ValueError("burst does not fit the frame window")
    power = np.mean(np.abs(burst) ** 2)
    x = np.zeros(n, dtype=complex)
    samples = np.arange(len(burst))
    x[delay:delay + len(burst)] = (burst * rms / np.sqrt(power)
                                     * np.exp(1j * (rng.uniform(0, 2 * np.pi) + cfo / SPS * samples)))
    noise = rms ** 2 * SPS / 10 ** (snr_db / 10)
    x += np.sqrt(noise / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return np.clip(np.round(x.real), -ADC_MAX - 1, ADC_MAX) + 1j * np.clip(np.round(x.imag), -ADC_MAX - 1, ADC_MAX)
