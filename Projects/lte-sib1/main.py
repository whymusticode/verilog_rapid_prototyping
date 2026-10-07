"""LTE SIB1 receiver on a continuous Pluto ADC stream (FDD, normal CP).

generate(samples) returns the stream sim.py measures: the raw 12-bit complex
ADC codes of one LTE downlink as a Pluto sees it, and the bit stream a receiver
must output. Each run draws one random cell (lte_dl.py has the transmitter and
the reference receiver): PCI, SFN, 1/2/4 CRS ports, CFI, PHICH configuration,
SIB1 DCI format (1A localized/distributed or 1C), allocation and code rate,
background traffic, a two-path channel per port, noise, and one crystal error
that sets both the carrier offset and the sample-clock drift. The stream starts
at a random point of a frame.

Output, per SIB1 transmission the reference receiver found, in time order: a
32-bit descriptor (CRC24A passed 1, PCI 9, SFN 10, TBS 12; most significant bit
first) then TBS payload hard decisions. Like a UE, the reference soft-combines
each transmission with the earlier ones of its 80 ms SIB1 period (redundancy
versions 0, 2, 3, 1; versions 1 and 2 alone are often not decodable), so CRC and
payload are those of the combined decode. Each bit is determined once the SIB1
subframe has fully arrived (ready); the reference decodes every record from
the samples up to that point only, as a streaming receiver must.

`python3 main.py` decodes random cells for time_budget_s and reports, per SNR,
how many SIB1 transmissions the reference found and decoded, and its payload
bit errors against what was transmitted.
"""
from pathlib import Path
import math
import sys
import time

import numpy as np
import yaml

PROJECT = Path(__file__).resolve().parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import lte_dl  # noqa: E402

with (PROJECT / "params.yaml").open() as params_file:
    params = yaml.safe_load(params_file)

lte_dl.turbo_core.approx_star = bool(params["approximate"])
FS = float(params["target"]["sample_rate"])
FIELDS = (("crc", 1), ("pci", 9), ("sfn", 10), ("tbs", 12))
MARGIN = lte_dl.Ofdm(FS).cp0
# The receiver knows its crystal tolerance: search carrier offsets 20% beyond it.
MAX_CFO = 1.2 * params["clock_ppm"] * 1e-6 * params["carrier_hz"]


def random_cell(rng) -> lte_dl.TxConfig:
    """A random cell whose SIB1 allocation is valid and below max_code_rate."""
    n_rb = int(params["n_rb"])
    while True:
        ports = int(rng.choice(params["ports"]))
        phich_dur = int(rng.random() < params["extended_phich"])
        cfi = 3 if phich_dur else int(rng.integers(1, 4))
        pci = int(rng.integers(504))
        fmt = str(rng.choice(["1A", "1C"]))
        gap2 = n_rb >= 50 and rng.random() < 0.5
        if fmt == "1A":
            distributed = bool(rng.random() < 0.5)
            gap2 = gap2 and distributed
            span = lte_dl.n_vrb(n_rb, gap2) if distributed else n_rb
            L = int(rng.integers(2, 11))
            mcs, n1a = int(rng.integers(0, 27)), int(rng.choice([2, 3]))
        else:
            distributed = True
            step = lte_dl.n_step(n_rb)
            span = min(lte_dl.n_vrb(n_rb, gap2), step * (lte_dl.n_vrb(n_rb, False) // step))
            L = step * int(rng.integers(1, 4))
            mcs, n1a = int(rng.integers(0, 32)), 3
        if L > span:
            continue
        start = int(rng.integers(0, span - L + 1))
        if fmt == "1C":
            start -= start % lte_dl.n_step(n_rb)
        # Common search space (36.213 9.1.1): 4 candidates of 4 CCEs, 2 of 8.
        aggregation = int(rng.choice([4, 8]))
        phich_res = int(rng.integers(4))
        regs = lte_dl.control_layout(n_rb, ports, lte_dl.n_control(cfi, n_rb), pci, phich_dur, phich_res)[2]
        n_cce = len(regs) // 9
        if n_cce < aggregation:
            continue
        candidate = int(rng.integers(min(4 if aggregation == 4 else 2, n_cce // aggregation)))
        cfg = lte_dl.TxConfig(n_rb=n_rb, pci=pci, ports=ports, cfi=cfi, phich_dur=phich_dur,
                              phich_res=phich_res, sfn0=int(rng.integers(1024)), fmt=fmt,
                              distributed=distributed, gap2=gap2, vrb_start=start, n_vrb=L, mcs=mcs,
                              n1a=n1a, aggregation=aggregation, candidate=candidate,
                              plmn=((f"{rng.integers(200, 800)}", f"{rng.integers(0, 1000):03d}"[:int(rng.choice([2, 3]))]),),
                              tac=int(rng.integers(1 << 16)), cell_identity=int(rng.integers(1 << 28)),
                              band=int(rng.integers(1, 65)))
        g = lte_dl.grant(fmt, cfg.dci(), n_rb)
        if not g["valid"]:
            continue
        G = 2 * len(lte_dl.pdsch_res(n_rb, pci, ports, 5, lte_dl.n_control(cfi, n_rb), g["prbs"])[0])
        if (g["tbs"] + 24) / G <= params["max_code_rate"]:
            return cfg


def run(samples, rng):
    """One cell: (ADC stream, SIB1 records, cell description)."""
    cfg = random_cell(rng)
    g = lte_dl.grant(cfg.fmt, cfg.dci(), cfg.n_rb)
    head = lte_dl.encode_sib1(cfg.plmn, cfg.tac, cfg.cell_identity, cfg.band)
    payload = np.array((head + list(rng.integers(0, 2, g["tbs"])))[:g["tbs"]], np.uint8)
    ppm = float(rng.uniform(-1, 1) * params["clock_ppm"])
    snr = float(rng.choice(params["snr_db"]))
    frame = 10 * 15 * round(FS / 15e3) * (1 + ppm * 1e-6)
    offset = int(rng.integers(0, int(frame)))
    n_frames = math.ceil((samples + offset) / frame) + 1
    rx, truth = lte_dl.transmit(cfg, FS, n_frames, rng, snr_db=snr, cfo=-ppm * 1e-6 * params["carrier_hz"],
                                ppm=ppm, traffic=float(params["traffic"]), payload=payload)
    rx = rx[offset:offset + samples + int(frame)]
    scale = params["adc_rms"] / np.sqrt(np.mean(np.abs(rx) ** 2))
    codes = (np.clip(np.round(rx.real * scale), -2048, 2047)
             + 1j * np.clip(np.round(rx.imag * scale), -2048, 2047))
    sf_len = frame / 10
    records = []
    for f in range(n_frames):
        sfn = (cfg.sfn0 + f) % 1024
        start = f * frame + 5 * sf_len - offset
        # Done once the subframe has arrived as the receiver times it: one CP of
        # margin covers the channel delay and the receiver's timing estimate.
        ready = math.ceil(start + sf_len + MARGIN)
        if sfn % 2 or start < 0 or ready > len(codes):
            continue
        try:
            report = lte_dl.receive(codes[:ready], FS, max_cfo=MAX_CFO, iterations=int(params["iterations"]),
                                    log=lambda *_: None)
        except ValueError:
            continue
        entry = report["sib1"][-1] if report["sib1"] else None
        if entry is None or "dci" not in entry or abs(entry["start"] - start) > sf_len / 2:
            continue
        records.append(dict(ready=ready, crc=int(entry["crc_combined"]), pci=report["cell"].pci,
                            sfn=entry["sfn"], tbs=entry["grant"]["tbs"], payload=entry["hard_combined"],
                            combined=entry["combined"], truth_sfn=sfn))
    return codes, records, dict(cfg=cfg, snr_db=snr, ppm=ppm, payload=payload)


def descriptor(record) -> list[int]:
    return [b for name, width in FIELDS for b in lte_dl.int_to_bits(int(record[name]), width)]


def generate(samples, rng=None):
    """The input stream and expected output bit stream for sim.py."""
    rng = rng or np.random.default_rng()
    codes, records, _ = run(samples, rng)
    bits, ready, names = [], [], []
    for r in records:
        record = descriptor(r) + list(r["payload"])
        bits += record
        ready += [r["ready"]] * len(record)
        names += [name for name, width in FIELDS for _ in range(width)] + ["payload"] * r["tbs"]
    names = np.array(names)
    groups = {name: names == name for name in ("payload", *(f for f, _ in FIELDS))}
    return dict(x=codes, y=np.array(bits, dtype=float), ready=np.array(ready, dtype=np.int64),
                groups=groups, primary="payload")


if __name__ == "__main__":
    started = time.monotonic()
    rng = np.random.default_rng()
    stats = {}
    cells = 0
    while time.monotonic() - started < float(params["time_budget_s"]):
        codes, records, info = run(int(params["sim_samples"]), rng)
        cells += 1
        s = stats.setdefault(info["snr_db"], dict(found=0, crc=0, bits=0, errors=0))
        for r in records:
            s["found"] += 1
            s["crc"] += r["crc"]
            if len(r["payload"]) == len(info["payload"]):
                s["bits"] += len(r["payload"])
                s["errors"] += int(np.sum(r["payload"] != info["payload"]))
    print(f"{cells} cells, {params['sim_samples']} samples each, {time.monotonic() - started:.1f} s")
    print(f"{'SNR dB':>6} {'found':>6} {'crc ok':>6} {'bits':>8} {'errors':>7} {'BER':>9}")
    for snr in sorted(stats):
        s = stats[snr]
        ber = s["errors"] / s["bits"] if s["bits"] else float("nan")
        print(f"{snr:>6g} {s['found']:>6} {s['crc']:>6} {s['bits']:>8} {s['errors']:>7} {ber:>9.2e}")
