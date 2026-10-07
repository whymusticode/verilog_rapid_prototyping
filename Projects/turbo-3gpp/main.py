"""LTE turbo receiver on a continuous Pluto ADC stream.

generate(samples) returns the stream sim.py measures: the raw ADC samples the
receiver sees (complex 12-bit I/Q, no padding, no side channel) and the bit
stream it must output. Bursts arrive at random offsets with every parameter
drawn independently per burst (unseeded) and carry their own in-band header
(rx_stream.py). Output, per packet in order of completion: a 33-bit
descriptor (CRC accepted 1, A-1 14, Q_m index 2, S 16; most significant bit
first) then A payload hard decisions. Each bit is determined once the packet's
last used sample has arrived (ready). How many bits travel per AXI beat is the
RTL's choice. `python3 main.py` streams for time_budget_s and reports the
reference receiver's BER against the transmitted bits per noise level.
"""
from pathlib import Path
import sys
import time

import numpy as np
import yaml

PROJECT = Path(__file__).resolve().parent
for directory in (PROJECT, PROJECT / "python"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import rx_stream
import tx_stream

with (PROJECT / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

# Es/N0 (dB) where this receiver's decoded payload BER is 1e-1, 1e-2 and 1e-3,
# by (Q_m, nominal rate), measured once with A=2048 (256QAM 5/6 extrapolated).
# Each burst uses one of these or a clean point 10 dB above the 1e-3 point.
OPERATING_POINTS = {
    (2, 0.3333): (-0.64, -0.09, 0.19),
    (2, 0.5): (1.47, 2.02, 2.48),
    (2, 0.6667): (3.03, 3.9, 4.36),
    (2, 0.75): (3.58, 4.78, 5.15),
    (2, 0.8333): (3.96, 5.81, 6.18),
    (4, 0.3333): (3.86, 4.38, 4.77),
    (4, 0.5): (6.57, 7.2, 7.6),
    (4, 0.6667): (8.67, 9.76, 10.19),
    (4, 0.75): (9.41, 10.8, 11.3),
    (4, 0.8333): (9.88, 12.07, 12.56),
    (6, 0.3333): (7.73, 8.22, 8.51),
    (6, 0.5): (11.01, 11.69, 11.99),
    (6, 0.6667): (13.59, 14.77, 15.23),
    (6, 0.75): (14.54, 16.17, 16.67),
    (6, 0.8333): (15.12, 17.63, 18.27),
    (8, 0.3333): (10.84, 11.56, 11.94),
    (8, 0.5): (15.17, 15.98, 16.56),
    (8, 0.6667): (18.32, 19.68, 20.29),
    (8, 0.75): (19.53, 21.39, 22.07),
    (8, 0.8333): (20.11, 22.85, 23.67),
}
LEVELS = ("1e-1", "1e-2", "1e-3", "clean")
CLEAN_MARGIN_DB = 10
FIELDS = (("crc", 1), ("length", 14), ("modulation", 2), ("symbols", 16))


def largest_payload(q_m, rate, samples):
    """Largest A (16 to 16384) whose burst at this Q_m and rate fits `samples`, or None."""
    fits = lambda A: (tx_stream.burst_length(A, q_m, rate) <= samples and
                      rx_stream.valid_geometry(A, tx_stream.geometry(A, q_m, rate), q_m, params["max_burst"]))
    low, high = 16, 1 << 14
    if not fits(low):
        return None
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if fits(middle) else (low, middle - 1)
    return low


def random_transport(rng):
    """One burst with every parameter drawn independently at random."""
    q_m = int(rng.choice(rx_stream.MODULATIONS))
    rate = float(rng.choice(tx_stream.RATES))
    level = str(rng.choice(LEVELS))
    top = largest_payload(q_m, rate, params["max_burst"])
    A = int(np.exp(rng.uniform(np.log(16), np.log(top + 1))))
    points = OPERATING_POINTS[q_m, round(rate, 4)]
    snr_db = points[2] + CLEAN_MARGIN_DB if level == "clean" else points[LEVELS.index(level)]
    return dict(payload=rng.integers(0, 2, A), Q_m=q_m, G=tx_stream.geometry(A, q_m, rate), rate=rate,
                level=level, snr_db=snr_db, cfo=rng.uniform(-.95, .95), fraction=rng.random(),
                phase=rng.uniform(0, 2 * np.pi), gap=tx_stream.MIN_GAP + int(rng.integers(257)))


def descriptor(packet):
    values = (int(packet["crc"]), packet["A"] - 1, rx_stream.MODULATIONS.index(packet["Q_m"]), packet["S"])
    return [(value >> shift) & 1 for value, (_, width) in zip(values, FIELDS)
            for shift in range(width - 1, -1, -1)]


def run(samples=None, deadline=None, rng=None):
    """Transmit random bursts and receive them until `samples` input samples
    (plus one max_burst so output already started can finish) or `deadline`.
    Returns the ADC stream, the transmitted bursts and the received packets."""
    rng = rng or np.random.default_rng()
    receiver = rx_stream.StreamReceiver(params["iterations_x2"], params["approximate"], params["max_burst"])
    pieces, transports, packets, length = [], [], [], 0
    goal = None if samples is None else samples + params["max_burst"]
    while (goal is None or length < goal) and (deadline is None or time.monotonic() < deadline):
        t = random_transport(rng)
        segment, (offset,) = tx_stream.stream([t], rng)
        segment = segment[:len(segment) - tx_stream.MIN_GAP]     # stream() pads after the burst
        t["start"] = length + offset
        transports.append(t)
        pieces.append(segment)
        length += len(segment)
        packets += receiver.push(segment)
    return np.concatenate(pieces), transports, packets


def generate(samples):
    """The input stream and expected output bit stream for sim.py."""
    x, _, packets = run(samples)
    bits, ready, names = [], [], []
    for packet in packets:
        record = descriptor(packet) + list(packet["payload"])
        bits += record
        ready += [packet["last"] + 1] * len(record)
        names += [name for name, width in FIELDS for _ in range(width)] + ["payload"] * packet["A"]
    names = np.array(names)
    groups = {name: names == name for name in ("payload", *(f for f, _ in FIELDS))}
    return dict(x=x, y=np.array(bits, dtype=float), ready=np.array(ready), groups=groups, primary="payload")


if __name__ == "__main__":
    started = time.monotonic()
    x, transports, packets = run(deadline=started + float(params["time_budget_s"]))
    found = {packet["start"]: packet for packet in packets}
    complete = [t for t in transports
                if t["start"] + tx_stream.burst_length(len(t["payload"]), t["Q_m"], t["rate"]) <= len(x)]
    busy = sum(tx_stream.burst_length(len(t["payload"]), t["Q_m"], t["rate"]) for t in complete)
    out_bits = sum(len(descriptor(p)) + p["A"] for p in packets)
    print(f"{len(x)} samples; {len(complete)} transports, {len(packets)} packets received; bursts occupy "
          f"{busy / len(x):.1%} of samples; {out_bits / len(x):.3f} output bits per input sample; "
          f"{time.monotonic() - started:.1f} s")
    print(f"{'level':>6} {'sent':>5} {'missed':>6} {'crc ok':>6} {'bits':>8} {'bit errors':>10} {'BER':>9}")
    for level in LEVELS:
        group = [t for t in complete if t["level"] == level]
        missed = errors = bits = accepted = 0
        for t in group:
            packet = next((found[s] for s in range(t["start"] - 4, t["start"] + 5) if s in found), None)
            if packet is None or packet["A"] != len(t["payload"]):
                missed += 1
                continue
            accepted += packet["crc"]
            bits += len(t["payload"])
            errors += int(np.count_nonzero(packet["payload"] != t["payload"]))
        ber = f"{errors / bits:.3g}" if bits else "n/a"
        print(f"{level:>6} {len(group):5d} {missed:6d} {accepted:6d} {bits:8d} {errors:10d} {ber:>9}")
    print("BER counts only received packets; missed bursts are listed separately.")
