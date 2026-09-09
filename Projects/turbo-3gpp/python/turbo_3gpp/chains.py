"""Stateful equivalents of the MATLAB System objects (GPL-3.0-or-later)."""
import numpy as np
from .core import (get_3gpp_crc_polynomial, get_crc_generator_matrix,
    get_3gpp_code_block_segment_lengths, get_3gpp_encoded_code_block_segment_lengths,
    internal_interleaver, rate_matching, generate_and_append_crc_bits,
    code_block_segmentation, turbo_encoder, code_block_concatenation,
    code_block_deconcatenation, turbo_decoder, code_block_desegmentation,
    check_and_remove_crc_bits)


class turbo_coding_chain:
    """Configure using MATLAB property names, e.g. ``A=40, G=132``.

    ``step`` (or calling the object) lazily sets up the chain. Tunable
    properties update rate matching; ``release`` unlocks structural properties.
    """
    _defaults = dict(A=16, I_LBRM=0, N_IR=np.inf, rv_idx=0, G=132, N_L=1, Q_m=1)
    _structural = {'A', 'I_LBRM', 'N_IR'}

    def __init__(self, **properties):
        self._ready = False
        for name, value in self._defaults.items():
            setattr(self, name, properties.pop(name, value))
        if properties:
            raise TypeError(f'Unknown properties: {sorted(properties)}')

    def __setattr__(self, name, value):
        if name in self._structural and getattr(self, '_ready', False):
            raise ValueError(f'{name} is nontunable; call release() first')
        if name in {'A', 'N_IR', 'G'} and value < 0:
            raise ValueError(f'{name} should not be negative')
        if name == 'rv_idx' and value not in (0,1,2,3):
            raise ValueError('Valid rv_idx values are 0, 1, 2 and 3')
        if name == 'N_L' and value < 1:
            raise ValueError('N_L should be no less than 1')
        if name == 'Q_m' and value not in (1,2,4,6,8,10):
            raise ValueError('Unsupported Q_m')
        object.__setattr__(self, name, value)

    CRC_polynomial_TB = property(lambda s: get_3gpp_crc_polynomial('CRC24A'))
    CRC_polynomial_CB = property(lambda s: get_3gpp_crc_polynomial('CRC24B') if s.C > 1 else np.array([1]))
    L_TB = property(lambda s: len(s.CRC_polynomial_TB)-1)
    L_CB = property(lambda s: len(s.CRC_polynomial_CB)-1)
    B = property(lambda s: s.A+s.L_TB)
    C = property(lambda s: len(s.K_r))
    B_prime = property(lambda s: s.B if s.B <= 6144 else s.B+s.C*s.L_CB)
    K_r = property(lambda s: get_3gpp_code_block_segment_lengths(s.B))
    F_r = property(lambda s: np.r_[sum(s.K_r)-s.B_prime, np.zeros(s.C-1, dtype=int)])
    D_r = property(lambda s: s.K_r+4)
    E_r = property(lambda s: get_3gpp_encoded_code_block_segment_lengths(s.G,s.C,s.N_L,s.Q_m))
    N_ref = property(lambda s: np.floor(s.N_IR/s.C))

    def setupImpl(self):
        self.CRC_generator_matrix_TB = get_crc_generator_matrix(sum(self.K_r), self.CRC_polynomial_TB)
        self.CRC_generator_matrix_CB = (get_crc_generator_matrix(6144, self.CRC_polynomial_CB)
                                        if self.C > 1 else np.empty((0,0)))
        self.internal_interleaver_patterns = [internal_interleaver(np.arange(k)) for k in self.K_r]
        self.processTunedPropertiesImpl()

    def processTunedPropertiesImpl(self):
        self.rate_matching_patterns = []
        for D, F, E in zip(self.D_r, self.F_r, self.E_r):
            d = np.arange(3*D, dtype=float).reshape(3,D,order='F')
            d[:2,:F] = np.nan
            self.rate_matching_patterns.append(rate_matching(d,self.N_ref,self.I_LBRM,self.rv_idx,int(E)).astype(int))
        self._tuned = (self.rv_idx,self.G,self.N_L,self.Q_m)

    def step(self, *args):
        if not self._ready:
            self.setupImpl()
            self._ready = True
        elif self._tuned != (self.rv_idx,self.G,self.N_L,self.Q_m):
            self.processTunedPropertiesImpl()
        return self.stepImpl(*args)

    def __call__(self, *args):
        return self.step(*args)

    def reset(self):
        if self._ready and isinstance(self, turbo_decoding_chain):
            self.resetImpl()

    def release(self):
        self._ready = False


class turbo_encoding_chain(turbo_coding_chain):
    def stepImpl(self, a):
        b = generate_and_append_crc_bits(a,self.CRC_generator_matrix_TB)
        blocks = code_block_segmentation(b,self.K_r,self.CRC_generator_matrix_CB)
        return code_block_concatenation([
            turbo_encoder(c,pi).ravel(order='F')[pattern]
            for c,pi,pattern in zip(blocks,self.internal_interleaver_patterns,self.rate_matching_patterns)])


class turbo_decoding_chain(turbo_coding_chain):
    _defaults = dict(turbo_coding_chain._defaults, I_HARQ=0, iterations=8)
    _structural = turbo_coding_chain._structural | {'I_HARQ'}

    def setupImpl(self):
        super().setupImpl()
        self.resetImpl()

    def stepImpl(self, f):
        blocks = code_block_deconcatenation(f,self.E_r)
        decoded, iterations = [], []
        for r, e in enumerate(blocks):
            v = np.zeros(3*self.D_r[r])
            np.add.at(v,self.rate_matching_patterns[r],e)
            d = v.reshape(3,self.D_r[r],order='F')
            d[:2,:self.F_r[r]] = np.nan
            if self.I_HARQ:
                self.buffers[r] += d
                d = self.buffers[r]
            crc = self.CRC_generator_matrix_CB if self.C > 1 else self.CRC_generator_matrix_TB
            c, it = turbo_decoder(d,self.internal_interleaver_patterns[r],self.iterations,crc)
            decoded.append(c)
            iterations.append(it)
        b = code_block_desegmentation(decoded,self.B,self.CRC_generator_matrix_CB)
        a = check_and_remove_crc_bits(b,self.CRC_generator_matrix_TB) if len(b) else np.array([])
        return a, np.array(iterations)

    def resetImpl(self):
        self.buffers = [np.zeros((3,d)) for d in self.D_r]
