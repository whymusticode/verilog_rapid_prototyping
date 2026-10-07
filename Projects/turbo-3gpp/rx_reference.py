"""Raw-IQ packet interface: rx_phy front end, then the unchanged turbo_decoding_chain."""
import numpy as np
from turbo_3gpp import core, turbo_decoding_chain
import rx_phy

# Lanes: 0 = I, 1 = Q (ADC codes), 2 = control. Control integers occupy lane 2,
# one field per beat. N_IR=0 represents infinity.
FIELDS = ("version", "A", "G", "rv_idx", "Q_m", "N_L", "N_IR", "I_LBRM",
          "I_HARQ", "iterations_x2", "approximate", "pid", "new_data")
DEFAULTS = dict(version=1, A=40, G=192, rv_idx=0, Q_m=1, N_L=1, N_IR=0,
                I_LBRM=0, I_HARQ=0, iterations_x2=8, approximate=1,
                pid=0, new_data=1)


def configuration(values):
    """Convert wire fields to the source chain's constructor arguments."""
    return {key: (np.inf if key == "N_IR" and values[key] == 0 else values[key])
            for key in ("A", "G", "rv_idx", "Q_m", "N_L", "N_IR", "I_LBRM")}


def make_frame(n, iq, **settings):
    """n beats of [I, Q, control] from an n-sample complex ADC window."""
    unknown = settings.keys() - DEFAULTS.keys()
    if unknown:
        raise ValueError(f"unknown configuration fields: {sorted(unknown)}")
    values = dict(DEFAULTS, **settings)
    iq = np.asarray(iq, dtype=complex)
    if iq.shape != (n,) or n < len(FIELDS):
        raise ValueError("IQ window must hold exactly n samples")
    frame = np.zeros((n, 3))
    frame[:, 0], frame[:, 1] = iq.real, iq.imag
    frame[:len(FIELDS), 2] = [values[key] for key in FIELDS]
    return frame


class Receiver:
    def __init__(self, n, harq_processes=8):
        if n < len(FIELDS) or harq_processes < 1:
            raise ValueError("insufficient frame capacity or HARQ processes")
        self.n = n
        self.harq_processes = harq_processes
        self.contexts = {}

    def reset(self):
        self.contexts.clear()

    def unpack(self, frame):
        frame = np.asarray(frame, dtype=float)
        if frame.shape == (self.n * 3,):
            frame = frame.reshape(self.n, 3)
        if frame.shape != (self.n, 3):
            raise ValueError(f"expected ({self.n}, 3) input frame")
        header = frame[:len(FIELDS), 2]
        if not np.all(np.isfinite(header)) or np.any(header != np.floor(header)):
            raise ValueError("configuration fields must be finite integers")
        v = dict(zip(FIELDS, map(int, header)))
        if v["version"] != 1 or not 1 <= v["A"] <= self.n or not 0 <= v["G"] <= self.n:
            raise ValueError("unsupported version or packet exceeds frame capacity")
        if v["rv_idx"] not in range(4) or v["Q_m"] not in (1, 2, 4, 6, 8, 10):
            raise ValueError("unsupported redundancy version or modulation order")
        if v["N_L"] < 1 or v["N_IR"] < 0 or v["iterations_x2"] < 0:
            raise ValueError("invalid layer count, buffer limit or iteration count")
        if any(v[key] not in (0, 1) for key in ("I_LBRM", "I_HARQ", "approximate", "new_data")):
            raise ValueError("flags must be zero or one")
        if not 0 <= v["pid"] < self.harq_processes:
            raise ValueError("HARQ process id exceeds configured capacity")
        if not v["I_HARQ"] and not v["new_data"]:
            raise ValueError("continuation requires HARQ")
        if v["G"] % v["Q_m"]:
            raise ValueError("G must be a whole number of Q_m-bit symbols")
        if rx_phy.SEARCH + 16 + rx_phy.SPS * rx_phy.burst_symbols(v["G"], v["Q_m"]) > self.n:
            raise ValueError("burst for G bits does not fit the frame window")
        if not np.all(np.isfinite(frame[:, :2])):
            raise ValueError("IQ samples must be finite")
        lengths = core.get_3gpp_code_block_segment_lengths(v["A"] + 24)
        E = core.get_3gpp_encoded_code_block_segment_lengths(v["G"], len(lengths), v["N_L"], v["Q_m"])
        if sum(E) != v["G"]:
            raise ValueError("source rate-matching lengths do not sum to G for this configuration")
        llrs = rx_phy.demodulate(frame[:, 0] + 1j * frame[:, 1], v["G"], v["Q_m"])
        return v, llrs

    def process(self, frame):
        v, llrs = self.unpack(frame)
        structural = tuple(v[key] for key in ("A", "N_IR", "I_LBRM"))
        if v["I_HARQ"] and not v["new_data"]:
            if v["pid"] not in self.contexts:
                raise ValueError("HARQ continuation without an initial transaction")
            previous, decoder = self.contexts[v["pid"]]
            if previous != structural:
                raise ValueError("HARQ structural configuration changed without new_data")
            for key in ("G", "rv_idx", "Q_m", "N_L"):
                setattr(decoder, key, v[key])
            decoder.iterations = v["iterations_x2"] / 2
        else:
            decoder = turbo_decoding_chain(**configuration(v), I_HARQ=v["I_HARQ"],
                                           iterations=v["iterations_x2"] / 2)
            # Reusing a process id for new data always discards its old buffer.
            self.contexts.pop(v["pid"], None)
        previous_mode = core.approx_star
        try:
            core.approx_star = bool(v["approximate"])
            decoded, iterations = decoder(llrs)
        finally:
            core.approx_star = previous_mode
        if v["I_HARQ"]:
            self.contexts[v["pid"]] = (structural, decoder)
        output = np.zeros((self.n, 3))
        output[:len(decoded), 0] = decoded
        # CRC validity, decoded length, block count, process id, redundancy version.
        output[:5, 1] = [int(len(decoded) == v["A"]), len(decoded), len(iterations), v["pid"], v["rv_idx"]]
        output[:len(iterations), 2] = iterations
        return output
