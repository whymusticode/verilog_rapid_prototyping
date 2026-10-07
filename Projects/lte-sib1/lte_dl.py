"""LTE FDD downlink receiver for the MIB and SIB1 (normal cyclic prefix), plus a
matching transmitter for self-tests.

Section numbers refer to 3GPP TS 36.211 (physical channels), 36.212 (coding),
36.213 (procedures) and 36.331 (RRC). SIB1's transport block goes through the
project's own turbo_3gpp chain (CRC24A, rate matching with any redundancy
version, turbo decoding), so a passing CRC here is the same check the RTL makes.

Grid convention: every OFDM symbol is held on the 110-RB maximum grid (1320
subcarriers, DC between indices 659 and 660). A cell with n_rb resource blocks
occupies [660 - 6 n_rb, 660 + 6 n_rb); its own subcarrier k is grid index
k + 6 (110 - n_rb). CRS, PBCH and sync positions are then independent of n_rb.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from turbo_3gpp import core as turbo_core  # noqa: E402
from turbo_3gpp import turbo_decoding_chain, turbo_encoding_chain  # noqa: E402

MAX_RB = 110
DC = 6 * MAX_RB                       # grid index of the first subcarrier above DC
GRID = 2 * DC
SYNC = np.arange(DC - 36, DC + 36)    # central 72 subcarriers: PSS, SSS, PBCH
PSS_K = np.arange(DC - 31, DC + 31)   # d(n), n = 0..61 (6.11.1.2)
SQ2 = math.sqrt(2)
SI_RNTI = 0xFFFF
BANDWIDTHS = (6, 15, 25, 50, 75, 100)
PHICH_NG = (1 / 6, 1 / 2, 1, 2)
CRS_SYMBOLS = {0: (0, 4), 1: (0, 4), 2: (1,), 3: (1,)}   # symbols within a slot (6.10.1.2)


def bits_to_int(bits) -> int:
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return value


def int_to_bits(value: int, width: int) -> list[int]:
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


# ---------------------------------------------------------------- sequences

_X1 = np.zeros(0, np.uint8)


def _gold_x1(n: int) -> np.ndarray:
    """x1 of the length-31 Gold sequence (7.2); it does not depend on c_init."""
    global _X1
    if len(_X1) < n + 31:
        m = max(n + 31, 40000)
        x = np.zeros(m, np.uint8)
        x[0] = 1
        for i in range(0, m - 31, 28):   # x(i+31) needs x(i..i+3): 28 at a time
            j = min(28, m - 31 - i)
            x[i + 31:i + 31 + j] = x[i + 3:i + 3 + j] ^ x[i:i + j]
        _X1 = x
    return _X1


@lru_cache(maxsize=8192)
def _gold(c_init: int, length: int) -> np.ndarray:
    n = 1600 + length
    x1 = _gold_x1(n)
    x2 = np.zeros(n + 31, np.uint8)
    x2[:31] = (c_init >> np.arange(31)) & 1
    for i in range(0, n, 28):
        j = min(28, n - i)
        x2[i + 31:i + 31 + j] = (x2[i + 3:i + 3 + j] ^ x2[i + 2:i + 2 + j]
                                 ^ x2[i + 1:i + 1 + j] ^ x2[i:i + j])
    out = x1[1600:n] ^ x2[1600:n]
    out.flags.writeable = False
    return out


def gold(c_init: int, length: int) -> np.ndarray:
    """Pseudo-random sequence c(n), n < length (36.211 7.2)."""
    return _gold(int(c_init), int(length))


def pss(nid2: int) -> np.ndarray:
    u = (25, 29, 34)[nid2]
    n = np.arange(62)
    m = np.where(n < 31, n * (n + 1), (n + 1) * (n + 2))
    return np.exp(-1j * np.pi * u * m / 63)


def _mseq(taps) -> np.ndarray:
    x = [0, 0, 0, 0, 1]
    for i in range(26):
        x.append(sum(x[i + t] for t in taps) % 2)
    return 1 - 2 * np.array(x)


_S, _C, _Z = _mseq((2, 0)), _mseq((3, 0)), _mseq((4, 2, 1, 0))


def sss(nid1: int, nid2: int, subframe: int) -> np.ndarray:
    """6.11.2.1; subframe is 0 or 5."""
    qp = nid1 // 30
    q = (nid1 + qp * (qp + 1) // 2) // 30
    mp = nid1 + q * (q + 1) // 2
    m0 = mp % 31
    m1 = (m0 + mp // 31 + 1) % 31
    n = np.arange(31)
    s0, s1 = _S[(n + m0) % 31], _S[(n + m1) % 31]
    c0, c1 = _C[(n + nid2) % 31], _C[(n + nid2 + 3) % 31]
    z0, z1 = _Z[(n + m0 % 8) % 31], _Z[(n + m1 % 8) % 31]
    d = np.empty(62)
    if subframe == 0:
        d[0::2], d[1::2] = s0 * c0, s1 * c1 * z0
    else:
        d[0::2], d[1::2] = s1 * c0, s0 * c1 * z1
    return d


@lru_cache(maxsize=4096)
def crs_seq(ns: int, ls: int, pci: int) -> np.ndarray:
    """r_{l,ns}(m'), m' < 220 (6.10.1.1), normal CP."""
    c = gold(2 ** 10 * (7 * (ns + 1) + ls + 1) * (2 * pci + 1) + 2 * pci + 1, 4 * MAX_RB)
    return ((1 - 2.0 * c[0::2]) + 1j * (1 - 2.0 * c[1::2])) / SQ2


def crs_v(port: int, ls: int, ns: int) -> int:
    if port < 2:
        return (0 if ls == 0 else 3) if port == 0 else (3 if ls == 0 else 0)
    return 3 * (ns % 2) + (3 if port == 3 else 0)


def crs_grid(port: int, ls: int, ns: int, pci: int, lo: int, hi: int) -> np.ndarray:
    kk = 6 * np.arange(2 * MAX_RB) + (crs_v(port, ls, ns) + pci % 6) % 6
    return kk[(kk >= lo) & (kk < hi)]


# ---------------------------------------------------------------- OFDM

def grid_freq(kk) -> np.ndarray:
    kk = np.asarray(kk)
    return np.where(kk < DC, kk - DC, kk - DC + 1)


class Ofdm:
    """Normal-CP OFDM at fs = N * 15 kHz (N a multiple of 128)."""

    def __init__(self, fs: float):
        n = fs / 15e3
        N = int(round(n))
        if abs(n - N) > 1e-6 or N % 128:
            raise ValueError(f"sample rate {fs:g} must be a multiple of 1.92 MS/s")
        self.fs, self.N = fs, N
        self.cp0, self.cp = 160 * N // 2048, 144 * N // 2048
        self.sf = 15 * N
        starts, t = [], 0
        for l in range(14):
            c = self.cp0 if l % 7 == 0 else self.cp
            starts.append(t + c)
            t += c + N
        self.starts = np.array(starts)
        self.slot = self.sf // 2
        f = grid_freq(np.arange(GRID))
        self.valid = np.abs(f) < N // 2
        self.bins = f % N
        # Windows start early inside the CP to tolerate timing error and
        # multipath; the ramp undoes the resulting linear phase.
        self.backoff = self.cp // 3
        self.ramp = np.exp(2j * np.pi * f * self.backoff / N)
        self.max_rb = min(MAX_RB, (N // 2 - 1) // 6)

    def demod(self, x: np.ndarray, pos: float):
        p = int(round(pos)) - self.backoff
        if p < 0 or p + self.N > len(x):
            return None
        F = np.fft.fft(x[p:p + self.N])
        out = np.zeros(GRID, complex)
        out[self.valid] = F[self.bins[self.valid]] * self.ramp[self.valid]
        return out

    def modulate(self, grid: np.ndarray) -> np.ndarray:
        out = []
        for l in range(14):
            F = np.zeros(self.N, complex)
            F[self.bins[self.valid]] = grid[l, self.valid]
            s = np.fft.ifft(F)
            c = self.cp0 if l % 7 == 0 else self.cp
            out.append(np.r_[s[-c:], s])
        return np.concatenate(out)

    def pss_template(self, nid2: int) -> np.ndarray:
        F = np.zeros(self.N, complex)
        F[self.bins[PSS_K]] = pss(nid2)
        t = np.fft.ifft(F)
        return t / np.linalg.norm(t)


# ---------------------------------------------------------------- coding

G_CONV = (0o133, 0o171, 0o165)
_TAPS = np.array([[(g >> (6 - j)) & 1 for j in range(7)] for g in G_CONV])
_OUT = np.zeros((64, 2, 3), np.int8)     # state bit i holds input c(k-1-i)
for _s in range(64):
    for _u in (0, 1):
        _OUT[_s, _u] = (_TAPS @ np.array([_u] + [(_s >> i) & 1 for i in range(6)])) % 2
_PRED = np.array([[(ns >> 1) | (b << 5) for b in (0, 1)] for ns in range(64)])
_PRED_SIGN = 1 - 2.0 * _OUT[_PRED, (np.arange(64) & 1)[:, None]]     # (64, 2, 3)
P_CONV = (1, 17, 9, 25, 5, 21, 13, 29, 3, 19, 11, 27, 7, 23, 15, 31,
          0, 16, 8, 24, 4, 20, 12, 28, 2, 18, 10, 26, 6, 22, 14, 30)


def conv_encode(c) -> np.ndarray:
    """Tail-biting rate-1/3 convolutional code (36.212 5.1.3.1), streams concatenated."""
    c = np.asarray(c, dtype=int)
    K = len(c)
    reg = np.array([np.roll(c, j) for j in range(7)])          # reg[j][k] = c(k - j) mod K
    return ((_TAPS @ reg) % 2).astype(np.uint8).ravel()


@lru_cache(maxsize=1024)
def conv_interleave(D: int) -> np.ndarray:
    """Sub-block interleaver of 36.212 5.1.4.2.1: output position -> input index (-1 = NULL)."""
    R = -(-D // 32)
    nd = 32 * R - D
    return np.array([32 * r + P_CONV[j] - nd for j in range(32) for r in range(R)])


@lru_cache(maxsize=1024)
def conv_rm_index(D: int, E: int) -> np.ndarray:
    """e(k) = d[index(k)] for convolutionally coded blocks (5.1.4.2)."""
    v = conv_interleave(D)
    v = v[v >= 0]
    w = np.concatenate([s * D + v for s in range(3)])
    return w[np.arange(E) % len(w)]


def viterbi(acc: np.ndarray, K: int) -> np.ndarray:
    """Tail-biting soft Viterbi over three wraps; acc is stream-major (3, K) LLRs."""
    L = np.tile(np.asarray(acc, float).reshape(3, K).T, (3, 1))
    metric = np.zeros(64)
    decisions = np.zeros((3 * K, 64), np.int8)
    for t in range(3 * K):
        cand = metric[_PRED] + _PRED_SIGN @ L[t]
        decisions[t] = np.argmax(cand, axis=1)
        metric = cand[np.arange(64), decisions[t]]
        metric -= metric.max()
    s = int(np.argmax(metric))
    out = np.zeros(3 * K, np.uint8)
    for t in range(3 * K - 1, -1, -1):
        out[t] = s & 1
        s = _PRED[s, decisions[t, s]]
    return out[K:2 * K]


def conv_decode(e: np.ndarray, D: int) -> np.ndarray:
    acc = np.zeros(3 * D)
    np.add.at(acc, conv_rm_index(D, len(e)), e)
    return viterbi(acc, D)


def crc16(bits) -> np.ndarray:
    reg = 0
    for b in bits:
        fb = ((reg >> 15) & 1) ^ int(b)
        reg = (reg << 1) & 0xFFFF
        if fb:
            reg ^= 0x1021
    return np.array(int_to_bits(reg, 16), np.uint8)


ANT_MASK = {1: np.zeros(16, np.uint8), 2: np.ones(16, np.uint8),
            4: np.array([0, 1] * 8, np.uint8)}
RNTI_MASK = np.array(int_to_bits(SI_RNTI, 16), np.uint8)


def crc_ok(payload, parity, mask) -> bool:
    return bool(np.array_equal(crc16(payload) ^ mask, np.asarray(parity, np.uint8)))


# ---------------------------------------------------------------- modulation

def qpsk(bits) -> np.ndarray:
    b = np.asarray(bits, float)
    return ((1 - 2 * b[0::2]) + 1j * (1 - 2 * b[1::2])) / SQ2


def qpsk_llr(d: np.ndarray, w: np.ndarray) -> np.ndarray:
    """LLR = log P(0)/P(1) per bit; positive means 0."""
    out = np.empty(2 * len(d))
    out[0::2], out[1::2] = w * d.real, w * d.imag
    return out


def _pairs(M: int, P: int):
    if P == 2:
        return [(np.arange(0, M - 1, 2), 0, 1)]
    return [(np.arange(0, M - 1, 4), 0, 2), (np.arange(2, M - 1, 4), 1, 3)]


def txdiv_encode(d: np.ndarray, P: int) -> np.ndarray:
    """Layer mapping and precoding for transmit diversity (6.3.3.3, 6.3.4.3)."""
    y = np.zeros((P, len(d)), complex)
    if P == 1:
        y[0] = d
        return y
    for a, p0, p1 in _pairs(len(d), P):
        b = a + 1
        y[p0, a], y[p1, a] = d[a], -np.conj(d[b])
        y[p0, b], y[p1, b] = d[b], np.conj(d[a])
    return y / SQ2


def txdiv_decode(r: np.ndarray, H: np.ndarray, sigma2: float):
    """Single-antenna receive: equalized symbols and the per-symbol LLR weight."""
    P = H.shape[0]
    if P == 1:
        g = np.abs(H[0]) ** 2 + 1e-12
        return r * np.conj(H[0]) / g, 2 * SQ2 * g / sigma2
    d = np.zeros_like(r)
    w = np.zeros(len(r))
    for a, p0, p1 in _pairs(len(r), P):
        b = a + 1
        h0 = (H[p0, a] + H[p0, b]) / 2
        h1 = (H[p1, a] + H[p1, b]) / 2
        g = np.abs(h0) ** 2 + np.abs(h1) ** 2 + 1e-12
        d[a] = (np.conj(h0) * r[a] + h1 * np.conj(r[b])) * SQ2 / g
        d[b] = (np.conj(h0) * r[b] - h1 * np.conj(r[a])) * SQ2 / g
        w[a] = w[b] = SQ2 * g / sigma2
    return d, w


# ---------------------------------------------------------------- cell search

@dataclass
class Cell:
    pci: int
    cfo: float               # Hz, removed from the samples
    frame0: float            # sample index of subframe 0 of frame 0 (may be negative)
    sf_len: float            # measured samples per subframe (includes sample-clock error)
    scale: float             # sf_len / nominal
    pss_score: float
    sss_score: float
    n_pss: int


def find_cell(x: np.ndarray, ofdm: Ofdm, max_cfo: float = 60e3, log=print):
    """PSS/SSS search; returns the cell and the CFO-corrected samples."""
    N, fs = ofdm.N, ofdm.fs
    D = N // 128
    xd = signal.resample_poly(x, 1, D) if D > 1 else np.asarray(x)
    half = 9600                                   # 5 ms at 1.92 MS/s
    span = min(len(xd), 6 * half)
    if span < half + 128:
        raise ValueError("need at least 5 ms of samples")
    seg = xd[:span]
    t = np.arange(span) / 1.92e6
    energy = np.convolve(np.abs(seg) ** 2, np.ones(128), "valid")
    folds = len(energy) // half
    den = energy[:folds * half].reshape(folds, half).sum(0) + 1e-30
    small = Ofdm(1.92e6)
    hyps = []
    # PSS correlation folded over half-frames, at 5 kHz CFO steps (the
    # 66.7 us PSS loses little coherence within 2.5 kHz).
    for f in np.arange(-max_cfo, max_cfo + 1, 5e3):
        xs = seg * np.exp(-2j * np.pi * f * t)
        for nid2 in range(3):
            c = signal.fftconvolve(xs, np.conj(small.pss_template(nid2)[::-1]), "valid")
            num = (np.abs(c[:folds * half]) ** 2).reshape(folds, half).sum(0)
            ratio = num / den
            i = int(np.argmax(ratio))
            hyps.append((float(ratio[i]), float(f), nid2, i))
    # Zadoff-Chu PSS correlation is ambiguous in whole subcarriers of CFO (a
    # frequency shift looks like a time shift), so refine the strongest distinct
    # hypotheses and keep the one whose SSS matches best.
    hyps.sort(reverse=True)
    picked = []
    for h in hyps:
        if all(h[2] != q[2] or abs(h[1] - q[1]) > 5e3 for q in picked):
            picked.append(h)
        if len(picked) == 4:
            break
    best = None
    for score, cfo, nid2, pos in picked:
        cell, xc = _refine(x, ofdm, score, cfo, nid2, pos * D)
        if best is None or cell.sss_score > best[0].sss_score:
            best = (cell, xc)
        if cell.sss_score > 0.8:
            break
    cell, xc = best
    log(f"PSS: N_ID2={cell.pci % 3}, correlation {cell.pss_score:.3f}"
        + ("  (weak: is the frequency right?)" if cell.pss_score < 0.1 else ""))
    log(f"SSS: N_ID1={cell.pci // 3} -> PCI {cell.pci}; CFO {cell.cfo:+.0f} Hz; "
        f"sample clock {(cell.scale - 1) * 1e6:+.2f} ppm; {cell.n_pss} PSS used; SSS match {cell.sss_score:.2f}")
    return cell, xc


def _refine(x, ofdm, score, cfo, nid2, guess):
    """Fine CFO, half-frame timing and SSS for one PSS hypothesis."""
    N, fs = ofdm.N, ofdm.fs
    T = ofdm.pss_template(nid2)
    step = 5e-3 * fs
    w = 4 * (N // 128) + 8
    n = np.arange(len(x))
    # Fine CFO from cyclic-prefix correlation over every symbol: unambiguous to
    # +-7.5 kHz and, unlike the Zadoff-Chu PSS, not coupled to timing error.
    for _ in range(2):
        xc = x * np.exp(-2j * np.pi * cfo * n / fs)
        idx, a, b, good = _fit(_track(xc, T, guess, step, w), step)
        cfo += _cp_cfo(xc, ofdm, a, b, len(idx))
    xc = x * np.exp(-2j * np.pi * cfo * n / fs)
    idx, a, b, good = _fit(_track(xc, T, guess, step, w), step)

    # SSS: coherent against the PSS channel, all half-frames, both parities.
    zs = []
    for i in idx[good]:
        p = a + b * i
        yp, ys = ofdm.demod(xc, p), ofdm.demod(xc, p - (N + ofdm.cp))
        if yp is None or ys is None:
            continue
        h = yp[PSS_K] * np.conj(pss(nid2))
        zs.append((i, (ys[PSS_K] * np.conj(h)).real))
    ze = sum((z for i, z in zs if i % 2 == 0), np.zeros(62))
    zo = sum((z for i, z in zs if i % 2 == 1), np.zeros(62))
    s0 = np.array([sss(n1, nid2, 0) for n1 in range(168)])
    s5 = np.array([sss(n1, nid2, 5) for n1 in range(168)])
    metric = np.array([s0 @ ze + s5 @ zo, s5 @ ze + s0 @ zo])
    parity, nid1 = np.unravel_index(np.argmax(metric), metric.shape)
    sss_score = float(metric[parity, nid1] / (np.abs(ze).sum() + np.abs(zo).sum() + 1e-30))
    sf_len = b / 5
    scale = sf_len / ofdm.sf
    frame0 = a - (ofdm.starts[6] + (5 * ofdm.sf if parity else 0)) * scale
    return Cell(int(3 * nid1 + nid2), float(cfo), float(frame0), float(sf_len), float(scale),
                score, sss_score, int(good.sum())), xc


def _fit(peaks, step):
    """Half-frame index -> PSS position, a + b i, from the strong peaks."""
    idx = np.arange(len(peaks))
    pos = np.array([p for p, _ in peaks], float)
    q = np.array([s for _, s in peaks])
    good = q > 0.3 * q.max()
    b, a = np.polyfit(idx[good], pos[good], 1) if good.sum() > 1 else (step, pos[0])
    return idx, a, b, good


def _cp_cfo(x, ofdm, a, b, halves) -> float:
    """CFO from each symbol's CP against the symbol's end; PSS at a + b i is symbol 6."""
    N, scale = ofdm.N, b / (5 * ofdm.sf)
    acc = 0j
    for i in range(-1, halves + 1):
        start = a + b * i - ofdm.starts[6] * scale
        for sf in range(5):
            for l in range(14):
                w = int(round(start + (sf * ofdm.sf + ofdm.starts[l]) * scale))
                c = ofdm.cp0 if l % 7 == 0 else ofdm.cp
                if w - c >= 0 and w + N <= len(x):
                    acc += np.vdot(x[w - c:w], x[w + N - c:w + N])
    return float(np.angle(acc) * ofdm.fs / (2 * np.pi * N))


def _track(x, T, guess, step, w):
    """PSS peaks every half-frame, each searched near the previous peak + 5 ms."""
    N = len(T)
    pred = guess - math.floor(guess / step) * step
    peaks = []
    while pred + w + N <= len(x):
        lo = max(0, int(round(pred)) - w)
        seg = x[lo:int(round(pred)) + w + N]
        c = signal.fftconvolve(seg, np.conj(T[::-1]), "valid")
        e = np.convolve(np.abs(seg) ** 2, np.ones(N), "valid") + 1e-30
        r = np.abs(c) ** 2 / e
        k = int(np.argmax(r))
        peaks.append((lo + k, float(r[k])))
        pred = lo + k + step
    return peaks


def subframe(xc: np.ndarray, ofdm: Ofdm, cell: Cell, j: int):
    """Grid (14, GRID) of absolute subframe j (frame j // 10, subframe j % 10)."""
    start = cell.frame0 + j * cell.sf_len
    Y = np.empty((14, GRID), complex)
    for l in range(14):
        y = ofdm.demod(xc, start + ofdm.starts[l] * cell.scale)
        if y is None:
            return None
        Y[l] = y
    return Y


def refine_cfo(xc: np.ndarray, ofdm: Ofdm, cell: Cell, subframes) -> float:
    """Residual CFO from port-0 CRS one slot apart (unambiguous to +-1 kHz)."""
    acc = 0j
    for j in subframes:
        Y = subframe(xc, ofdm, cell, j)
        if Y is None:
            continue
        s = j % 10
        kk = crs_grid(0, 0, 2 * s, cell.pci, DC - 36, DC + 36)
        a = Y[0, kk] * np.conj(crs_seq(2 * s, 0, cell.pci)[kk // 6])
        b = Y[7, kk] * np.conj(crs_seq(2 * s + 1, 0, cell.pci)[kk // 6])
        acc += np.vdot(a, b)
    return float(np.angle(acc) / (2 * np.pi * ofdm.slot / ofdm.fs))


# ---------------------------------------------------------------- channel

def _smooth(v: np.ndarray) -> np.ndarray:
    if len(v) < 3:
        return v.copy()
    s = np.empty_like(v)
    s[1:-1] = (v[:-2] + v[1:-1] + v[2:]) / 3
    s[0], s[-1] = (2 * v[0] + v[1]) / 3, (2 * v[-1] + v[-2]) / 3
    return s


def chest(Y: np.ndarray, pci: int, sub: int, ports: int, lo: int, hi: int):
    """CRS channel estimates H[port, symbol, subcarrier] over [lo, hi) and the noise variance."""
    kk_all = np.arange(lo, hi)
    H = np.zeros((ports, 14, GRID), complex)
    resid = []
    for p in range(ports):
        times, ests = [], []
        for slot in (0, 1):
            ns = 2 * sub + slot
            for ls in CRS_SYMBOLS[p]:
                kk = crs_grid(p, ls, ns, pci, lo, hi)
                raw = Y[7 * slot + ls, kk] * np.conj(crs_seq(ns, ls, pci)[kk // 6])
                sm = _smooth(raw)
                if p == 0:
                    resid.append(raw[1:-1] - sm[1:-1])
                times.append(7 * slot + ls)
                ests.append(np.interp(kk_all, kk, sm.real) + 1j * np.interp(kk_all, kk, sm.imag))
        times, ests = np.array(times), np.array(ests)
        for l in range(14):
            j = int(np.searchsorted(times, l))
            if j == 0:
                e = ests[0]
            elif j == len(times):
                e = ests[-1]
            else:
                a = (l - times[j - 1]) / (times[j] - times[j - 1])
                e = (1 - a) * ests[j - 1] + a * ests[j]
            H[p, l, lo:hi] = e
    r = np.concatenate(resid)
    sigma2 = 1.5 * float(np.mean(np.abs(r) ** 2)) + 1e-15
    return H, sigma2


# ---------------------------------------------------------------- PBCH / MIB

@lru_cache(maxsize=512)
def pbch_res(pci: int):
    """PBCH resource elements in mapping order (6.6.4): k first, then l, slot 1 of subframe 0."""
    L, K = [], []
    for l in (7, 8, 9, 10):
        for kk in SYNC:
            if l in (7, 8) and (kk - pci % 6) % 3 == 0:
                continue                      # reserved for CRS of ports 0..3
            L.append(l)
            K.append(kk)
    return np.array(L), np.array(K)


PBCH_RM = conv_rm_index(40, 1920)


def mib_bits(n_rb: int, phich_dur: int, phich_res: int, sfn: int) -> np.ndarray:
    return np.array(int_to_bits(BANDWIDTHS.index(n_rb), 3) + [phich_dur]
                    + int_to_bits(phich_res, 2) + int_to_bits(sfn >> 2, 8) + [0] * 10, np.uint8)


def decode_mib(Y, H, sigma2, pci):
    """Try 1, 2 and 4 ports and the four 10 ms PBCH positions; the CRC mask picks the ports."""
    L, K = pbch_res(pci)
    r = Y[L, K]
    c = gold(pci, 1920)
    for P in (1, 2, 4):
        d, w = txdiv_decode(r, H[:P, L, K], sigma2)
        llr = qpsk_llr(d, w)
        for q in range(4):
            acc = np.zeros(120)
            np.add.at(acc, PBCH_RM[480 * q:480 * q + 480], llr * (1 - 2.0 * c[480 * q:480 * q + 480]))
            bits = viterbi(acc, 40)
            if crc_ok(bits[:24], bits[24:], ANT_MASK[P]):
                b = bits[:24]
                bw = bits_to_int(b[0:3])
                if bw >= len(BANDWIDTHS):
                    continue
                return dict(n_rb=BANDWIDTHS[bw], phich_dur=int(b[3]), phich_res=bits_to_int(b[4:6]),
                            sfn=(bits_to_int(b[6:14]) << 2) + q, ports=P)
    return None


# ---------------------------------------------------------------- control region

CFI_CODE = {1: np.array([0, 1, 1] * 10 + [0, 1], np.uint8),
            2: np.array([1, 0, 1] * 10 + [1, 0], np.uint8),
            3: np.array([1, 1, 0] * 10 + [1, 1], np.uint8)}


def pcfich_starts(n_rb: int, pci: int) -> list[int]:
    kbar = 6 * (pci % (2 * n_rb))
    return [(kbar + (i * n_rb // 2) * 6) % (12 * n_rb) for i in range(4)]


def _reg_size(l: int, ports: int) -> int:
    return 6 if l == 0 or (l == 1 and ports == 4) else 4


def reg_res(l: int, k: int, ports: int, pci: int, n_rb: int) -> list[int]:
    """Grid indices of the four REs of the REG starting at cell subcarrier k (6.2.4).
    Symbol 0 always skips the port 0 and 1 CRS positions, even for one port."""
    off = 6 * (MAX_RB - n_rb)
    if _reg_size(l, ports) == 6:
        return [k + j + off for j in range(6) if (k + j - pci % 6) % 3]
    return [k + j + off for j in range(4)]


@lru_cache(maxsize=256)
def control_layout(n_rb, ports, n_ctrl, pci, phich_dur, phich_res):
    """PCFICH REG starts, PHICH REGs (6.9.3) and the PDCCH REGs in mapping order (6.8.5)."""
    nsym = max(n_ctrl, 3 if phich_dur else 1)
    pcf = pcfich_starts(n_rb, pci)
    avail = [[k for k in range(0, 12 * n_rb, _reg_size(l, ports)) if not (l == 0 and k in pcf)]
             for l in range(nsym)]
    n0 = len(avail[0])
    phich = []
    for m in range(math.ceil(PHICH_NG[phich_res] * n_rb / 8)):
        for i in range(3):
            li = i if phich_dur else 0
            nl = len(avail[li])
            phich.append((li, avail[li][(pci * nl // n0 + m + i * nl // 3) % nl]))
    taken = set(phich) | {(0, k) for k in pcf}
    regs = tuple((l, k) for k in range(12 * n_rb) for l in range(n_ctrl)
                 if k % _reg_size(l, ports) == 0 and (l, k) not in taken)
    return tuple(pcf), tuple(phich), regs


def n_control(cfi: int, n_rb: int) -> int:
    return cfi + (1 if n_rb <= 10 else 0)


def decode_pcfich(Y, H, sigma2, n_rb, pci, ports, sub):
    ks = np.array([kk for k in pcfich_starts(n_rb, pci) for kk in reg_res(0, k, ports, pci, n_rb)])
    d, w = txdiv_decode(Y[0, ks], H[:ports, 0, ks], sigma2)
    llr = qpsk_llr(d, w) * (1 - 2.0 * gold((sub + 1) * (2 * pci + 1) * 512 + pci, 32))
    scores = {cfi: float(llr @ (1 - 2.0 * code)) for cfi, code in CFI_CODE.items()}
    return max(scores, key=scores.get), scores


def pdcch_llr(Y, H, sigma2, n_rb, pci, ports, sub, n_ctrl, phich_dur, phich_res):
    """Descrambled PDCCH LLRs in CCE order (72 per CCE) and the CCE count."""
    regs = control_layout(n_rb, ports, n_ctrl, pci, phich_dur, phich_res)[2]
    M = len(regs)
    ks = np.array([reg_res(l, k, ports, pci, n_rb) for l, k in regs])
    ls = np.repeat(np.array([l for l, _ in regs])[:, None], 4, 1)
    order = (np.arange(M) - pci) % M                   # w(j) = wbar((j - N_ID) mod M)
    r, h = Y[ls, ks][order], H[:ports][:, ls, ks][:, order]
    perm = conv_interleave(M)
    perm = perm[perm >= 0]                             # w(i) = z(perm(i))
    zr, zh = np.empty_like(r), np.empty_like(h)
    zr[perm], zh[:, perm] = r, h
    d, w = txdiv_decode(zr.ravel(), zh.reshape(ports, -1), sigma2)
    return qpsk_llr(d, w) * (1 - 2.0 * gold(sub * 512 + pci, 8 * M)), M // 9


# ---------------------------------------------------------------- DCI and resource allocation

AMBIGUOUS = {12, 14, 16, 20, 24, 26, 32, 40, 44, 56}


def rba_bits(n: int) -> int:
    return math.ceil(math.log2(n * (n + 1) / 2))


def size_1a(n_rb: int) -> int:
    s = 15 + rba_bits(n_rb)            # FDD; larger than format 0, so no padding to it
    return s + 1 if s in AMBIGUOUS else s


def n_gap(n_rb: int, gap2: bool) -> int:
    table = ((10, None, None), (11, 4, None), (19, 8, None), (26, 12, None), (44, 18, None),
             (49, 27, None), (63, 27, 9), (79, 32, 16), (110, 48, 16))
    for top, g1, g2 in table:
        if n_rb <= top:
            g1 = math.ceil(n_rb / 2) if g1 is None else g1
            if gap2 and g2 is None:
                raise ValueError(f"N_gap2 is undefined for {n_rb} RBs")
            return g2 if gap2 else g1
    raise ValueError(n_rb)


def n_vrb(n_rb: int, gap2: bool) -> int:
    g = n_gap(n_rb, gap2)
    return (n_rb // (2 * g)) * 2 * g if gap2 else 2 * min(g, n_rb - g)


def n_step(n_rb: int) -> int:
    return 2 if n_rb < 50 else 4


def size_1c(n_rb: int) -> int:
    n = n_vrb(n_rb, False) // n_step(n_rb)
    return (1 if n_rb >= 50 else 0) + rba_bits(n) + 5


def riv_decode(riv: int, N: int):
    L, s = riv // N + 1, riv % N
    if L + s > N:
        L, s = N - L + 2, N - 1 - s
    return s, L


def riv_encode(s: int, L: int, N: int) -> int:
    return N * (L - 1) + s if L - 1 <= N // 2 else N * (N - L + 1) + (N - 1 - s)


def rbg_size(n_rb: int) -> int:
    return 1 if n_rb <= 10 else 2 if n_rb <= 26 else 3 if n_rb <= 63 else 4


def vrb_to_prb(v: int, n_rb: int, gap2: bool):
    """Distributed VRB -> (PRB in slot 0, PRB in slot 1), 36.211 6.2.3.2."""
    g = n_gap(n_rb, gap2)
    Nt = 2 * g if gap2 else n_vrb(n_rb, False)
    P = rbg_size(n_rb)
    rows = math.ceil(Nt / (4 * P)) * P
    nulls = 4 * rows - Nt
    nt, base = v % Nt, Nt * (v // Nt)
    p1 = 2 * rows * (nt % 2) + nt // 2 + base
    p2 = rows * (nt % 4) + nt // 4 + base
    if nulls and nt >= Nt - nulls:
        prb = p1 - rows + (nulls // 2 if nt % 2 == 0 else 0)
    elif nulls and nt % 4 >= 2:
        prb = p2 - nulls // 2
    else:
        prb = p2
    odd = (prb - base + Nt // 2) % Nt + base

    def gap(t):
        return t + g - Nt // 2 if t - base >= Nt // 2 else t
    return gap(prb), gap(odd)


# 36.213 Table 7.1.7.2.1-1, columns N_PRB = 2 and 3 (format 1A with SI-RNTI).
TBS_1A = ((32, 56), (56, 88), (72, 144), (104, 176), (120, 208), (144, 224), (176, 256),
          (224, 328), (256, 392), (296, 456), (328, 504), (376, 584), (440, 680), (488, 744),
          (552, 840), (600, 904), (632, 968), (696, 1064), (776, 1160), (840, 1288),
          (904, 1384), (1000, 1480), (1064, 1608), (1128, 1736), (1192, 1800), (1256, 1864),
          (1480, 2216))
# 36.213 Table 7.1.7.2.3-1 (format 1C).
TBS_1C = (40, 56, 72, 120, 136, 144, 176, 208, 224, 256, 280, 296, 328, 336, 392, 488, 552,
          600, 632, 696, 776, 840, 904, 1000, 1064, 1128, 1224, 1288, 1384, 1480, 1608, 1736)


def grant(fmt: str, bits, n_rb: int) -> dict:
    """Downlink grant from a format 1A or 1C DCI addressed to SI-RNTI."""
    b = list(bits)
    if fmt == "1A":
        nr = rba_bits(n_rb)
        dist, rba = b[1], bits_to_int(b[2:2 + nr])
        i = 2 + nr
        mcs, ndi = bits_to_int(b[i:i + 5]), b[i + 8]
        rv, tpc = bits_to_int(b[i + 9:i + 11]), bits_to_int(b[i + 11:i + 13])
        s, L = riv_decode(rba, n_rb)
        gap2 = bool(dist and n_rb >= 50 and ndi)
        n1a = 3 if tpc & 1 else 2
        tbs = TBS_1A[mcs][n1a - 2] if mcs < len(TBS_1A) else None
        info = dict(fmt=fmt, distributed=bool(dist), gap2=gap2, vrb_start=s, n_vrb=L,
                    mcs=mcs, n_prb_1a=n1a, rv=rv, tbs=tbs)
    else:
        gap2 = bool(b[0]) if n_rb >= 50 else False
        i = 1 if n_rb >= 50 else 0
        n = n_vrb(n_rb, False) // n_step(n_rb)
        nr = rba_bits(n)
        s, L = riv_decode(bits_to_int(b[i:i + nr]), n)
        s, L = s * n_step(n_rb), L * n_step(n_rb)
        itbs = bits_to_int(b[i + nr:i + nr + 5])
        dist = True
        info = dict(fmt=fmt, distributed=True, gap2=gap2, vrb_start=s, n_vrb=L,
                    tbs_index=itbs, rv=None, tbs=TBS_1C[itbs])
    vrbs = range(s, s + L)
    if dist:
        pairs = [vrb_to_prb(v, n_rb, gap2) for v in vrbs]
        info["prbs"] = (sorted(p for p, _ in pairs), sorted(q for _, q in pairs))
    else:
        info["prbs"] = (list(vrbs), list(vrbs))
    info["valid"] = (info["tbs"] is not None and all(0 <= p < n_rb for p in info["prbs"][0] + info["prbs"][1]))
    return info


def dci_1a(n_rb, distributed, gap2, s, L, mcs, rv, n1a) -> np.ndarray:
    bits = ([1, int(distributed)] + int_to_bits(riv_encode(s, L, n_rb), rba_bits(n_rb))
            + int_to_bits(mcs, 5) + [0, 0, 0] + [int(gap2) if distributed and n_rb >= 50 else 0]
            + int_to_bits(rv, 2) + [0, int(n1a == 3)])
    return np.array(bits + [0] * (size_1a(n_rb) - len(bits)), np.uint8)


def dci_1c(n_rb, gap2, s, L, itbs) -> np.ndarray:
    n = n_vrb(n_rb, False) // n_step(n_rb)
    st = n_step(n_rb)
    bits = (([int(gap2)] if n_rb >= 50 else []) + int_to_bits(riv_encode(s // st, L // st, n), rba_bits(n))
            + int_to_bits(itbs, 5))
    return np.array(bits, np.uint8)


def find_dci(llr: np.ndarray, n_cce: int, n_rb: int, rnti: int = SI_RNTI) -> list[dict]:
    """Blind decoding of the common search space (36.213 9.1.1) for formats 1A and 1C."""
    mask = np.array(int_to_bits(rnti, 16), np.uint8)
    found, seen = [], set()
    for L, ncand in ((4, 4), (8, 2)):
        if n_cce // L == 0:
            continue
        for m in range(ncand):
            c0 = L * (m % (n_cce // L))
            e = llr[72 * c0:72 * (c0 + L)]
            for fmt, A in (("1A", size_1a(n_rb)), ("1C", size_1c(n_rb))):
                bits = conv_decode(e, A + 16)
                if not crc_ok(bits[:A], bits[A:], mask) or (fmt == "1A" and bits[0] != 1):
                    continue
                key = (fmt, bits[:A].tobytes())
                if key not in seen:
                    seen.add(key)
                    found.append(dict(fmt=fmt, L=L, cce=c0, bits=bits[:A]))
    return found


# ---------------------------------------------------------------- PDSCH

def pdsch_res(n_rb, pci, ports, sub, start_sym, prbs):
    """PDSCH REs in mapping order (6.3.5): k first over the slot's PRBs, then l."""
    off = 6 * (MAX_RB - n_rb)
    vshift = pci % 6
    L, K = [], []
    for l in range(start_sym, 14):
        slot, ls = divmod(l, 7)
        ks = np.sort(np.concatenate([np.arange(12 * p, 12 * p + 12) for p in prbs[slot]])) + off
        drop = np.zeros(len(ks), bool)
        for p in range(ports):
            if ls in CRS_SYMBOLS[p]:
                drop |= (ks - vshift - crs_v(p, ls, 2 * sub + slot)) % 6 == 0
        if (sub in (0, 5) and l in (5, 6)) or (sub == 0 and 7 <= l <= 10):
            drop |= (ks >= SYNC[0]) & (ks <= SYNC[-1])
        ks = ks[~drop]
        L.extend([l] * len(ks))
        K.extend(ks)
    return np.array(L, int), np.array(K, int)


def pdsch_c_init(rnti: int, sub: int, pci: int) -> int:
    return rnti * 2 ** 14 + sub * 2 ** 9 + pci


def sib1_rv(sfn: int) -> int:
    """36.321 5.3.1: RV_K = ceil(3/2 k) mod 4, k = (SFN/2) mod 4."""
    return math.ceil(1.5 * ((sfn // 2) % 4)) % 4


# ---------------------------------------------------------------- SIB1 (36.331, UPER)

class _Reader:
    def __init__(self, bits):
        self.b, self.i = list(bits), 0

    def uint(self, n):
        if self.i + n > len(self.b):
            raise ValueError("SIB1 ended early")
        v = bits_to_int(self.b[self.i:self.i + n])
        self.i += n
        return v

    def bit(self):
        return self.uint(1)


def parse_sib1(bits) -> dict:
    r = _Reader(bits)
    if r.bit():
        return dict(message="messageClassExtension")
    if not r.bit():
        return dict(message="SystemInformation (not SIB1)")
    has_pmax, _tdd, _ext = r.bit(), r.bit(), r.bit()
    has_csg = r.bit()
    plmns = []
    for _ in range(r.uint(3) + 1):
        mcc = "".join(str(r.uint(4)) for _ in range(3)) if r.bit() else None
        mnc = "".join(str(r.uint(4)) for _ in range(2 + r.bit()))
        plmns.append(dict(mcc=mcc, mnc=mnc, reserved_for_operator=r.bit() == 0))
    out = dict(message="SystemInformationBlockType1", plmns=plmns,
               tracking_area_code=r.uint(16), cell_identity=r.uint(28))
    out["enb_id"], out["cell_in_enb"] = out["cell_identity"] >> 8, out["cell_identity"] & 0xFF
    out["cell_barred"] = r.bit() == 0
    out["intra_freq_reselection"] = "allowed" if r.bit() == 0 else "notAllowed"
    out["csg_indication"] = bool(r.bit())
    if has_csg:
        out["csg_identity"] = r.uint(27)
    has_offset = r.bit()
    out["q_rx_lev_min_dbm"] = 2 * (r.uint(6) - 70)
    if has_offset:
        out["q_rx_lev_min_offset_db"] = 2 * (r.uint(3) + 1)
    if has_pmax:
        out["p_max_dbm"] = r.uint(6) - 30
    out["freq_band_indicator"] = r.uint(6) + 1
    return out


def encode_sib1(plmns, tac, cell_id, band, q_rx_lev_min_dbm=-128, p_max=None) -> list[int]:
    """The SIB1 fields parse_sib1 reads (for self-tests; the rest is zero padding)."""
    b = [0, 1, int(p_max is not None), 0, 0, 0] + int_to_bits(len(plmns) - 1, 3)
    for mcc, mnc in plmns:
        b += [1] + [x for d in mcc for x in int_to_bits(int(d), 4)] if mcc else [0]
        b += [len(mnc) - 2] + [x for d in mnc for x in int_to_bits(int(d), 4)] + [1]
    b += int_to_bits(tac, 16) + int_to_bits(cell_id, 28) + [1, 0, 0]
    b += [0] + int_to_bits(q_rx_lev_min_dbm // 2 + 70, 6)
    if p_max is not None:
        b += int_to_bits(p_max + 30, 6)
    return b + int_to_bits(band - 1, 6)


# ---------------------------------------------------------------- receiver

def receive(x: np.ndarray, fs: float, max_cfo: float = 60e3, iterations: int = 8, log=print) -> dict:
    """Cell search, MIB, then every SIB1 transmission in the capture."""
    ofdm = Ofdm(fs)
    cell, xc = find_cell(np.asarray(x, complex), ofdm, max_cfo, log)
    n_sf = int((len(x) - cell.frame0) // cell.sf_len) + 1
    first = math.ceil(-cell.frame0 / cell.sf_len)
    usable = [j for j in range(first, n_sf) if subframe(xc, ofdm, cell, j) is not None]
    df = refine_cfo(xc, ofdm, cell, usable[:40])
    cell.cfo += df
    xc = xc * np.exp(-2j * np.pi * df * np.arange(len(xc)) / fs)
    log(f"CRS: residual CFO {df:+.0f} Hz -> total {cell.cfo:+.0f} Hz")
    report = dict(cell=cell, mibs=[], sib1=[], combined=[])

    mib_frames = {}
    for j in usable:
        if j % 10:
            continue
        Y = subframe(xc, ofdm, cell, j)
        H, s2 = chest(Y, cell.pci, 0, 4, DC - 36, DC + 36)
        mib = decode_mib(Y, H, s2, cell.pci)
        snr = 10 * np.log10(np.mean(np.abs(H[0, 0, DC - 36:DC + 36]) ** 2) / s2)
        log(f"frame {j // 10}: " + (f"MIB SFN {mib['sfn']}, {mib['n_rb']} RB, {mib['ports']} port(s), "
                                    f"PHICH {'extended' if mib['phich_dur'] else 'normal'} "
                                    f"Ng={['1/6', '1/2', '1', '2'][mib['phich_res']]}"
                                    if mib else "MIB CRC failed") + f"  (CRS SNR {snr:.1f} dB)")
        if mib:
            mib_frames[j // 10] = mib
            report["mibs"].append(dict(frame=j // 10, snr_db=snr, **mib))
    if not mib_frames:
        log("no MIB decoded; stopping")
        return report
    votes = {}
    for m, mib in mib_frames.items():
        key = (mib["n_rb"], mib["ports"], mib["phich_dur"], mib["phich_res"], (mib["sfn"] - m) % 1024)
        votes[key] = votes.get(key, 0) + 1
    n_rb, ports, phich_dur, phich_res, sfn0 = max(votes, key=votes.get)
    report.update(n_rb=n_rb, ports=ports, phich_dur=phich_dur, phich_res=phich_res)
    if n_rb > ofdm.max_rb:
        need = 128 * math.ceil((12 * n_rb + 3) / 128) * 15e3
        log(f"{n_rb} RB needs a sample rate of at least {need / 1e6:g} MS/s; this capture is {fs / 1e6:g} MS/s")
        return report

    lo, hi = DC - 6 * n_rb, DC + 6 * n_rb
    windows = {}
    for j in usable:
        m, s = divmod(j, 10)
        sfn = (sfn0 + m) % 1024
        if s != 5 or sfn % 2:
            continue
        Y = subframe(xc, ofdm, cell, j)
        H, s2 = chest(Y, cell.pci, 5, ports, lo, hi)
        cfi, _ = decode_pcfich(Y, H, s2, n_rb, cell.pci, ports, 5)
        nc = n_control(cfi, n_rb)
        llr, n_cce = pdcch_llr(Y, H, s2, n_rb, cell.pci, ports, 5, nc, phich_dur, phich_res)
        entry = dict(sfn=sfn, cfi=cfi, n_cce=n_cce, crc=False, start=cell.frame0 + j * cell.sf_len)
        dcis = [d for d in find_dci(llr, n_cce, n_rb) if grant(d["fmt"], d["bits"], n_rb)["valid"]]
        if not dcis:
            log(f"SFN {sfn} subframe 5: CFI {cfi}, {n_cce} CCEs, no SI-RNTI DCI found")
            report["sib1"].append(entry)
            continue
        d = dcis[0]
        g = grant(d["fmt"], d["bits"], n_rb)
        rv = g["rv"] if g["rv"] is not None else sib1_rv(sfn)
        L, K = pdsch_res(n_rb, cell.pci, ports, 5, nc, g["prbs"])
        dd, w = txdiv_decode(Y[L, K], H[:ports, L, K], s2)
        bits_llr = qpsk_llr(dd, w) * (1 - 2.0 * gold(pdsch_c_init(SI_RNTI, 5, cell.pci), 2 * len(L)))
        hard, ok, it = turbo_decode([(bits_llr, rv)], g["tbs"], iterations)
        entry.update(dci=d["fmt"], aggregation=d["L"], cce=d["cce"], grant=g, rv=rv, G=len(bits_llr),
                     llr=bits_llr, crc=ok, iterations=it, hard=hard, bits=hard if ok else None)
        # A UE soft-combines the redundancy versions of each 80 ms SIB1 period:
        # this transmission together with the earlier ones of its period.
        period = windows.setdefault((sfn // 8, g["tbs"]), [])
        period.append((bits_llr, rv))
        if len(period) > 1:
            hard_c, ok_c, _ = turbo_decode(period, g["tbs"], iterations)
        else:
            hard_c, ok_c = hard, ok
        entry.update(combined=len(period), crc_combined=ok_c, hard_combined=hard_c)
        log(f"SFN {sfn} subframe 5: CFI {cfi}, DCI {d['fmt']} at CCE {d['cce']} (L={d['L']}), "
            f"PRBs {_ranges(g['prbs'][0])}, TBS {g['tbs']}, rv {rv}, G {len(bits_llr)}: "
            + (f"SIB1 CRC ok after {it:g} iterations" if ok else "SIB1 CRC failed")
            + (f"; combined with {len(period) - 1} earlier: " + ("ok" if ok_c else "failed")
               if len(period) > 1 else ""))
        report["sib1"].append(entry)
        if len(period) > 1:
            report["combined"].append(dict(period=sfn // 8, rvs=[r for _, r in period], crc=ok_c,
                                           bits=hard_c if ok_c else None))

    payload = next((e["bits"] for e in report["sib1"] if e.get("bits") is not None), None)
    if payload is None:
        payload = next((c["bits"] for c in report["combined"] if c["bits"] is not None), None)
    if payload is not None:
        report["sib1_bits"] = payload
        try:
            report["sib1_fields"] = parse_sib1(payload)
        except ValueError as error:
            report["sib1_fields"] = dict(error=str(error))
    return report


def turbo_decode(parts, tbs: int, iterations: int):
    """One transport block (a single code block, as for SIB1) from one or more
    transmissions [(llr, rv), ...], soft-combined after rate dematching. Returns
    the payload hard decisions whether or not CRC24A passes, the CRC result and
    the iterations used."""
    v = None
    for llr, rv in parts:
        ch = turbo_decoding_chain(A=tbs, G=len(llr), Q_m=2, rv_idx=rv, iterations=iterations)
        ch.setupImpl()
        if ch.C != 1:
            raise ValueError(f"TBS {tbs} needs {ch.C} code blocks")
        D, F = int(ch.D_r[0]), int(ch.F_r[0])
        v = np.zeros(3 * D) if v is None else v
        np.add.at(v, ch.rate_matching_patterns[0], llr)
    d = v.reshape(3, D, order="F")
    d[:2, :F] = np.nan
    c, it = turbo_core.turbo_decoder(d, ch.internal_interleaver_patterns[0], iterations,
                                     ch.CRC_generator_matrix_TB)
    b = c[F:]
    ok = len(turbo_core.check_and_remove_crc_bits(b, ch.CRC_generator_matrix_TB)) == tbs
    return b[:tbs].astype(np.uint8), ok, float(it)


def _ranges(prbs) -> str:
    prbs = sorted(prbs)
    if not prbs:
        return "-"
    out, start = [], prbs[0]
    for a, b in zip(prbs, prbs[1:] + [None]):
        if b != a + 1:
            out.append(f"{start}" if start == a else f"{start}-{a}")
            start = b
    return ",".join(out)


# ---------------------------------------------------------------- transmitter (self-tests)

@dataclass
class TxConfig:
    n_rb: int = 25
    pci: int = 101
    ports: int = 2
    cfi: int = 2
    phich_dur: int = 0
    phich_res: int = 1
    sfn0: int = 236
    fmt: str = "1A"
    distributed: bool = False
    gap2: bool = False
    vrb_start: int = 3
    n_vrb: int = 4
    mcs: int = 5            # 1A: I_TBS; 1C: TBS index
    n1a: int = 3
    aggregation: int = 4
    candidate: int = 1
    plmn: tuple = (("310", "410"),)
    tac: int = 0x2A3B
    cell_identity: int = 0x0ABCDE1
    band: int = 12

    def dci(self) -> np.ndarray:
        if self.fmt == "1A":
            return dci_1a(self.n_rb, self.distributed, self.gap2, self.vrb_start, self.n_vrb,
                          self.mcs, 0, self.n1a)
        return dci_1c(self.n_rb, self.gap2, self.vrb_start, self.n_vrb, self.mcs)


def transmit(cfg: TxConfig, fs: float, n_frames: int, rng, snr_db: float = 20.0,
             cfo: float = 0.0, ppm: float = 0.0, lead: int = 0, traffic: float = 0.0, payload=None):
    """A downlink with PSS/SSS, CRS, PBCH, PCFICH, PHICH filler, and SIB1 on PDCCH/PDSCH
    in subframe 5 of even frames, through a random two-tap channel per port. With
    traffic > 0, each other PRB of each subframe carries random QPSK with that
    probability, and the PDCCH of other subframes is filled with random QPSK.
    ppm stretches the sample clock (frames are 10 ms * fs * (1 + ppm 1e-6) long)."""
    ofdm = Ofdm(fs)
    P, n_rb, pci = cfg.ports, cfg.n_rb, cfg.pci
    lo, hi = DC - 6 * n_rb, DC + 6 * n_rb
    nc = n_control(cfg.cfi, n_rb)
    pcf, phich, regs = control_layout(n_rb, P, nc, pci, cfg.phich_dur, cfg.phich_res)
    g0 = grant(cfg.fmt, cfg.dci(), n_rb)
    assert g0["valid"], g0
    if payload is None:
        payload = np.array((encode_sib1(cfg.plmn, cfg.tac, cfg.cell_identity, cfg.band)
                            + [0] * g0["tbs"])[:g0["tbs"]], np.uint8)
    streams = [[] for _ in range(P)]
    for f in range(n_frames):
        sfn = (cfg.sfn0 + f) % 1024
        for s in range(10):
            G = np.zeros((P, 14, GRID), complex)
            for p in range(P):
                for slot in (0, 1):
                    for ls in CRS_SYMBOLS[p]:
                        kk = crs_grid(p, ls, 2 * s + slot, pci, lo, hi)
                        G[p, 7 * slot + ls, kk] = crs_seq(2 * s + slot, ls, pci)[kk // 6]
            if s in (0, 5):
                G[0, 6, PSS_K] = pss(pci % 3)
                G[0, 5, PSS_K] = sss(pci // 3, pci % 3, s)
            if s == 0:
                mib = mib_bits(n_rb, cfg.phich_dur, cfg.phich_res, sfn)
                coded = conv_encode(np.r_[mib, crc16(mib) ^ ANT_MASK[P]])[PBCH_RM]
                q = sfn % 4
                b = coded[480 * q:480 * q + 480] ^ gold(pci, 1920)[480 * q:480 * q + 480]
                L, K = pbch_res(pci)
                G[:, L, K] = txdiv_encode(qpsk(b), P)
            ks = [kk for k in pcf for kk in reg_res(0, k, P, pci, n_rb)]
            b = CFI_CODE[cfg.cfi] ^ gold((s + 1) * (2 * pci + 1) * 512 + pci, 32)
            G[:, 0, ks] = txdiv_encode(qpsk(b), P)
            for l, k in phich:
                G[0, l, reg_res(l, k, P, pci, n_rb)] = qpsk(rng.integers(0, 2, 8))
            sib1 = s == 5 and sfn % 2 == 0
            if traffic:
                busy = set(g0["prbs"][0]) | set(g0["prbs"][1]) if sib1 else set()
                prbs = [q for q in range(n_rb) if q not in busy and rng.random() < traffic]
                if prbs:
                    L, K = pdsch_res(n_rb, pci, P, s, nc, (prbs, prbs))
                    G[:, L, K] = qpsk(rng.integers(0, 2, (P, 2 * len(L))).ravel()).reshape(P, -1) / np.sqrt(P)
                if not sib1:
                    for l, k in regs:
                        G[:, l, reg_res(l, k, P, pci, n_rb)] = qpsk(rng.integers(0, 2, 8 * P)).reshape(P, 4) / np.sqrt(P)
            if sib1:
                M = len(regs)
                bits = rng.integers(0, 2, 8 * M).astype(np.uint8)
                dci = cfg.dci()
                if cfg.fmt == "1A":                    # 1A carries each transmission's rv
                    dci = dci_1a(n_rb, cfg.distributed, cfg.gap2, cfg.vrb_start, cfg.n_vrb,
                                 cfg.mcs, sib1_rv(sfn), cfg.n1a)
                A = len(dci)
                cw = conv_encode(np.r_[dci, crc16(dci) ^ RNTI_MASK])
                La = cfg.aggregation
                c0 = La * (cfg.candidate % ((M // 9) // La))
                bits[72 * c0:72 * (c0 + La)] = cw[conv_rm_index(A + 16, 72 * La)]
                y = txdiv_encode(qpsk(bits ^ gold(s * 512 + pci, 8 * M)), P).reshape(P, M, 4)
                perm = conv_interleave(M)
                w = y[:, perm[perm >= 0]]
                wbar = w[:, (np.arange(M) + pci) % M]
                for m, (l, k) in enumerate(regs):
                    G[:, l, reg_res(l, k, P, pci, n_rb)] = wbar[:, m]
                L, K = pdsch_res(n_rb, pci, P, 5, nc, g0["prbs"])
                e = turbo_encoding_chain(A=g0["tbs"], G=2 * len(L), Q_m=2,
                                         rv_idx=sib1_rv(sfn))(payload).astype(np.uint8)
                G[:, L, K] = txdiv_encode(qpsk(e ^ gold(pdsch_c_init(SI_RNTI, 5, pci), 2 * len(L))), P)
            for p in range(P):
                streams[p].append(ofdm.modulate(G[p]))
    delay = int(rng.integers(1, max(2, ofdm.cp // 2)))
    rx = 0
    for p in range(P):
        taps = np.zeros(delay + 1, complex)
        taps[0] = (rng.normal() + 1j * rng.normal()) / SQ2
        taps[delay] = 0.3 * (rng.normal() + 1j * rng.normal()) / SQ2
        t = np.concatenate(streams[p])
        rx = rx + np.convolve(t, taps)[:len(t)]
    if ppm:
        rx = signal.resample(rx, int(round(len(rx) * (1 + ppm * 1e-6))))
    rx = np.r_[np.zeros(lead, complex), rx]
    rx = rx * np.exp(2j * np.pi * cfo * np.arange(len(rx)) / fs)
    p = np.mean(np.abs(rx[lead:]) ** 2)
    rx = rx + np.sqrt(p / 10 ** (snr_db / 10) / 2) * (rng.normal(size=len(rx)) + 1j * rng.normal(size=len(rx)))
    return rx, dict(payload=payload, grant=g0, sfn0=cfg.sfn0, pci=pci, n_rb=n_rb, ports=P,
                    lead=lead, frame_len=10 * ofdm.sf * (1 + ppm * 1e-6))
