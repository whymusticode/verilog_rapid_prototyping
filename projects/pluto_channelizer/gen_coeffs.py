"""
Generate prototype lowpass filter coefficients for a 50-channel critically
sampled polyphase channelizer (20MHz in, 400kHz channel spacing).

Standard polyphase-channelizer design: prototype LPF cutoff near
fs/(2*M) = Nyquist of one channel, TAPS_PER_PHASE taps per polyphase
branch (M branches total => TAPS_PER_PHASE*M total taps).
"""
import numpy as np
from scipy.signal import firwin

M = 50
TAPS_PER_PHASE = 12   # moderate selectivity/cost tradeoff, typical channelizer design point
N_TAPS = TAPS_PER_PHASE * M

# cutoff at fs/(2M) (normalized to Nyquist = 1.0 -> cutoff = 1/M)
cutoff = 1.0 / M
h = firwin(N_TAPS, cutoff, window=('kaiser', 6.0))

# quantize to 16-bit signed coefficients (Coefficient_Width=16 in FIR Compiler default)
h_scaled = h / np.max(np.abs(h))
h_int = np.round(h_scaled * (2**15 - 1)).astype(int)
h_int = np.clip(h_int, -(2**15), 2**15 - 1)

print(f"N_TAPS={N_TAPS}, M={M}, TAPS_PER_PHASE={TAPS_PER_PHASE}")
print(",".join(str(int(x)) for x in h_int))

with open("/home/mbenton/verilog_rapid_prototyping/projects/pluto_channelizer/proto_coeffs.txt", "w") as f:
    f.write(",".join(str(int(x)) for x in h_int))
