"""NumPy port of Robert G. Maunder's LTE turbo routines.

Copyright (c) 2018 Robert G. Maunder; Python adaptations 2026.
SPDX-License-Identifier: GPL-3.0-or-later
Vectors are one-dimensional; interleaver indices remain zero-based.
"""
import math
import numpy as np
from ._qpp import QPP

# Corresponds to MATLAB's global approx_star; exact log-MAP by default.
approx_star = False


def get_3gpp_crc_polynomial(CRC):
    exponents = {'CRC24A': [24,23,18,17,14,11,10,7,6,5,4,3,1,0],
                 'CRC24B': [24,23,6,5,1,0], 'CRC16': [16,12,5,0],
                 'CRC8': [8,7,4,3,1,0]}
    if CRC not in exponents:
        raise ValueError('CRC is unsupported')
    e = exponents[CRC]
    p = np.zeros(max(e)+1)
    p[max(e)-np.array(e)] = 1
    return p


def get_crc_generator_matrix(A, crc_polynomial_pattern):
    p = np.asarray(crc_polynomial_pattern, dtype=float).reshape(-1)[1:]
    if not p.size:
        raise ValueError('crc_polynomial_pattern is invalid')
    g = np.zeros((A, p.size))
    if A:
        g[-1] = p
        for k in range(A-2, -1, -1):
            g[k] = np.logical_xor(np.r_[g[k+1, 1:], 0], g[k+1, 0]*p)
    return g


def calculate_crc_bits(a, G_max):
    a = np.asarray(a).reshape(-1)
    g = np.asarray(G_max)
    return (a @ g[g.shape[0]-a.size:]) % 2


def generate_and_append_crc_bits(a, G_max):
    return np.r_[a, calculate_crc_bits(a, G_max)]


def check_and_remove_crc_bits(b, G_max):
    b = np.asarray(b).reshape(-1)
    A = b.size - np.asarray(G_max).shape[1]
    a = b[:A]
    return a.copy() if np.array_equal(b[A:], calculate_crc_bits(a, G_max)) else np.array([])


def get_3gpp_code_block_segment_lengths(B):
    if B <= 0:
        raise ValueError('Unsupported block length')
    supported = np.array(sorted(QPP))
    C = 1 if B <= 6144 else math.ceil(B/6120)
    bp = B if C == 1 else B+24*C
    kp = supported[np.flatnonzero(C*supported >= bp)[0]]
    km = supported[np.flatnonzero(supported < kp)[-1]] if C > 1 else 0
    cm = math.floor((C*kp-bp)/(kp-km)) if C > 1 else 0
    return np.r_[np.full(cm, km), np.full(C-cm, kp)].astype(int)


def get_3gpp_encoded_code_block_segment_lengths(G, C, N_L, Q_m):
    # Preserve the source's G' (transpose), which is NOT G_prime.
    gp = G/(N_L*Q_m)
    gamma = G % C
    return N_L*Q_m*np.where(np.arange(C) <= C-gamma-1,
                           math.floor(gp/C), math.ceil(gp/C))


def code_block_segmentation(b, K_r, G_max):
    b = np.asarray(b).reshape(-1)
    ks = np.asarray(K_r, dtype=int).reshape(-1)
    L = np.asarray(G_max).shape[1] if len(ks) > 1 else 0
    F = int(sum(ks)-len(b)-len(ks)*L)
    if F < 0 or F > ks[0]-L:
        raise ValueError('Filler bits must fit in the first code block')
    blocks, offset = [], 0
    for r, k in enumerate(ks):
        f = F if r == 0 else 0
        a = np.r_[np.full(f, np.nan), b[offset:offset+k-L-f]]
        offset += k-L-f
        blocks.append(np.r_[a, calculate_crc_bits(np.nan_to_num(a), G_max)] if L else a)
    return blocks


def code_block_desegmentation(c_r, B, G_max):
    L = np.asarray(G_max).shape[1] if len(c_r) > 1 else 0
    F = sum(len(c) for c in c_r)-B-len(c_r)*L
    blocks = []
    for r, c in enumerate(c_r):
        c = np.asarray(c)
        a = c[:len(c)-L]
        if L and not np.array_equal(c[-L:], calculate_crc_bits(np.nan_to_num(a), G_max)):
            return np.array([])
        blocks.append(a[F if r == 0 else 0:])
    return code_block_concatenation(blocks)


def code_block_concatenation(e_r):
    return np.concatenate(e_r) if len(e_r) else np.array([])


def code_block_deconcatenation(f, E_r):
    f = np.asarray(f).reshape(-1)
    if len(f) != sum(E_r):
        raise ValueError('E_r should sum together to give G.')
    return list(np.split(f, np.cumsum(E_r, dtype=int)[:-1])) if len(E_r) else []


def internal_interleaver(c):
    c = np.asarray(c).reshape(-1)
    K = len(c)
    if K not in QPP:
        raise ValueError('K value not supported!')
    f1, f2 = QPP[K]
    i = np.arange(K, dtype=np.int64)
    return c[(f1*i+f2*i*i) % K]


def constituent_encoder(c):
    c = np.asarray(c).reshape(-1)
    K = len(c)
    x, z = np.zeros(K+3), np.zeros(K+3)
    s1 = s2 = s3 = 0
    for k in range(K+3):
        x[k] = c[k] if k < K else (s2+s3) % 2
        nxt = (c[k]+s2+s3) % 2 if k < K else 0
        z[k] = (nxt+s1+s3) % 2
        s1, s2, s3 = nxt, s1, s2
    return z, x


def turbo_encoder(c, pi):
    c = np.asarray(c, dtype=float).reshape(-1).copy()
    pi = np.asarray(pi, dtype=int)
    K = len(c)
    if len(pi) != K:
        raise ValueError('length of pi does not match K')
    filler = np.isnan(c)
    c[filler] = 0
    z, x = constituent_encoder(c)
    zp, xp = constituent_encoder(c[pi])
    d = np.zeros((3, K+4))
    d[:, :K] = [x[:K], z[:K], zp[:K]]
    d[:2, np.flatnonzero(filler)] = np.nan
    d[:, K:] = np.array([x[K],z[K],x[K+1],z[K+1],x[K+2],z[K+2],
                         xp[K],zp[K],xp[K+1],zp[K+1],xp[K+2],zp[K+2]]).reshape(3,4,order='F')
    return d


def subblock_interleaver(d, subblock_interleaver_index):
    d = np.asarray(d).reshape(-1)
    P = np.array([0,16,8,24,4,20,12,28,2,18,10,26,6,22,14,30,
                  1,17,9,25,5,21,13,29,3,19,11,27,7,23,15,31])
    R = math.ceil(len(d)/32)
    K = R*32
    y = np.r_[np.full(K-len(d), np.nan), d]
    if subblock_interleaver_index in (0, 1):
        return y.reshape(R,32)[:,P].ravel(order='F')
    if subblock_interleaver_index == 2:
        if K == 0:
            return y
        k = np.arange(K)
        return y[(P[k//R]+32*(k % R)+1) % K]
    raise ValueError('Unsupported subblock_interleaver_index')


def circular_buffer(v, N_ref, I_LBRM, rv_idx, E):
    v = np.asarray(v)
    if v.ndim != 2 or v.shape[0] != 3:
        raise ValueError('v should have three rows.')
    K = v.shape[1]
    if K % 32:
        raise ValueError('K_Pi should be a multiple of 32.')
    if rv_idx not in (0, 1, 2, 3):
        raise ValueError('Unsupported rv_id')
    if E == 0:
        return np.array([])
    R = K//32
    w = np.r_[v[0], v[1:].ravel(order='F')]
    n = int(3*K if I_LBRM == 0 else min(N_ref, 3*K))
    if n <= 0 or not np.any(~np.isnan(w[:n])):
        raise ValueError('Circular buffer has no selectable bits')
    k0 = R*(2*math.ceil(n/(8*R))*rv_idx+2)
    cycle = w[(k0+np.arange(n)) % n]
    return np.resize(cycle[~np.isnan(cycle)], E)


def rate_matching(d, N_ref, I_LBRM, rv_idx, E):
    v = np.array([subblock_interleaver(row, i) for i, row in enumerate(d)])
    return circular_buffer(v, N_ref, I_LBRM, rv_idx, E)


def maxstar(a, b=None):
    a = np.asarray(a, dtype=float)
    if b is not None:
        b = np.asarray(b, dtype=float)
        if approx_star:
            return np.fmax(a, b)
        with np.errstate(invalid='ignore'):
            sub = a-b
        sub = np.where(np.isnan(sub), 0, sub)
        return np.fmax(a,b)+np.log(1+np.exp(-np.abs(sub)))
    a = np.atleast_2d(a)
    if approx_star:
        return np.fmax.reduce(a, axis=1 if a.shape[0] == 1 else 0)
    c = a[0].copy()
    for row in a[1:]:
        c = maxstar(c, row)
    return c


_FROM = np.tile(np.arange(8), 2)
_TO = np.array([0,4,5,1,2,6,7,3,4,0,1,5,6,2,3,7])
_Z = np.array([0,0,1,1,1,1,0,0,1,1,0,0,0,0,1,1], dtype=bool)
_IN = np.array([np.flatnonzero(_TO == s) for s in range(8)])
_OUT = np.array([np.flatnonzero(_FROM == s) for s in range(8)])


def constituent_decoder(x_a, z_a):
    x_a, z_a = np.asarray(x_a).reshape(-1), np.asarray(z_a).reshape(-1)
    if len(x_a) != len(z_a):
        raise ValueError('LLR sequences must have the same length')
    n = len(x_a)
    gx, gz = np.zeros((16,n)), np.zeros((16,n))
    gx[8:] = -x_a
    gz[_Z] = -z_a
    g = gx+gz
    alpha, beta = np.zeros((8,n)), np.zeros((8,n))
    alpha[1:,0] = -np.inf
    beta[1:,-1] = -np.inf
    for k in range(1,n):
        t = alpha[_FROM,k-1]+g[:,k-1]
        alpha[:,k] = maxstar(t[_IN[:,0]], t[_IN[:,1]])
    for k in range(n-2,-1,-1):
        t = beta[_TO,k+1]+g[:,k+1]
        beta[:,k] = maxstar(t[_OUT[:,0]], t[_OUT[:,1]])
    delta = alpha[_FROM]+beta[_TO]+gz
    return maxstar(delta[:8])-maxstar(delta[8:])


def turbo_decoder(d_a, pi, max_iterations, G_max=None):
    d = np.asarray(d_a, dtype=float).copy()
    K = d.shape[1]-4
    pi = np.asarray(pi, dtype=int)
    if d.shape[0] != 3:
        raise ValueError('d_a should have 3 rows')
    if len(pi) != K:
        raise ValueError('length of pi does not match K')
    if max_iterations*2 != round(max_iterations*2):
        raise ValueError('iterations must be a multiple of 0.5')
    filler = np.flatnonzero(np.isnan(d[0]))
    d[np.isnan(d)] = np.inf
    ca = np.zeros(K)
    x, z, xp, zp = np.zeros((4,K+3))
    z[:K], zp[:K] = d[1,:K], d[2,:K]
    tail = d[:,K:].ravel(order='F')
    x[K:], z[K:], xp[K:], zp[K:] = tail[:6:2], tail[1:6:2], tail[6::2], tail[7::2]
    # Deliberately retain MATLAB linear indexing at iteration zero.
    c = (d.ravel(order='F')[:K] < 0).astype(float)
    done = 0.0
    if G_max is None or np.sum(calculate_crc_bits(c, G_max)) != 0:
        for i in range(1, math.ceil(max_iterations)+1):
            x[:K] = ca+d[0,:K]
            ce = constituent_decoder(x,z)[:K]+d[0,:K]
            c = ((ca+ce) < 0).astype(float)
            done = i-0.5
            if G_max is not None and np.sum(calculate_crc_bits(c,G_max)) == 0:
                break
            if i <= math.floor(max_iterations):
                xp[:K] = ce[pi]
                ca[pi] = constituent_decoder(xp,zp)[:K]
                c = ((ca+ce) < 0).astype(float)
                done = float(i)
                if G_max is not None and np.sum(calculate_crc_bits(c,G_max)) == 0:
                    break
        else:
            done = max_iterations
    c[filler] = np.nan
    return c, done
