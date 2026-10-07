#!/usr/bin/env python3
"""Capture an LTE downlink with a Pluto and decode the cell's MIB and SIB1.

SIB1 is the one broadcast message every cell sends with the LTE turbo code
(CRC24A, rate matching, redundancy versions 0, 2, 3, 1 over 80 ms). It is
scrambled only with the public SI-RNTI and cell ID, so a passing CRC24A shows
the whole chain - sync, OFDM, channel estimate, control channel, rate
dematching and turbo decoding - is right on a real signal. The decoded PLMN,
tracking area code and cell identity can be compared with the phone's
field-test screen.

Use the tower's downlink frequency (the band's DL range; the phone's EARFCN
gives it exactly). Examples:

    python3 sib1.py --freq 739e6                       # capture 100 ms and decode
    python3 sib1.py --freq 739e6 --save cell.npz       # also keep the capture
    python3 sib1.py --load cell.npz --llr sib1_llr.npz # decode a saved capture, export LLRs
    python3 sib1.py --selftest                         # synthetic cells through the receiver

The default 23.04 MS/s covers every LTE bandwidth up to 20 MHz. FDD, normal
cyclic prefix only.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lte_dl  # noqa: E402


def capture(uri: str, freq: float, fs: float, samples: int, gain: float | None) -> np.ndarray:
    """One contiguous buffer from the Pluto's AD9363 through libiio."""
    import iio
    ctx = iio.Context(uri)
    phy, rx = ctx.find_device("ad9361-phy"), ctx.find_device("cf-ad9361-lpc")
    phy.find_channel("altvoltage0", True).attrs["frequency"].value = str(int(freq))
    ch = phy.find_channel("voltage0", False)
    ch.attrs["sampling_frequency"].value = str(int(fs))
    ch.attrs["rf_bandwidth"].value = str(int(min(fs, 20e6)))
    if gain is None:
        ch.attrs["gain_control_mode"].value = "slow_attack"
    else:
        ch.attrs["gain_control_mode"].value = "manual"
        ch.attrs["hardwaregain"].value = str(gain)
    for name in ("voltage0", "voltage1"):
        rx.find_channel(name).enabled = True
    buf = iio.Buffer(rx, samples, False)
    buf.refill()                     # the first buffer may predate the settings; drop it
    buf.refill()
    raw = np.frombuffer(buf.read(), dtype=np.int16).astype(np.float32)
    print(f"captured {samples} samples at {fs / 1e6:g} MS/s, {freq / 1e6:.3f} MHz; "
          f"gain {ch.attrs['hardwaregain'].value}; peak {np.abs(raw).max():.0f} of 2048")
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64) / 2048


def load(path: Path, rate: float | None):
    if path.suffix == ".npz":
        data = np.load(path)
        return data["x"], float(data["fs"]), float(data["freq"]) if "freq" in data else None
    if rate is None:
        raise SystemExit("--rate is required for raw .cf32/.cs16 files")
    if path.suffix == ".cs16":
        raw = np.fromfile(path, np.int16).astype(np.float32)
        return (raw[0::2] + 1j * raw[1::2]) / 2048, rate, None
    return np.fromfile(path, np.complex64), rate, None


def show(report: dict, freq: float | None) -> None:
    cell = report["cell"]
    print()
    print(f"PCI {cell.pci}", end="")
    if freq:
        print(f"; carrier offset {cell.cfo:+.0f} Hz = {-cell.cfo / freq * 1e6:+.2f} ppm Pluto clock error", end="")
    print()
    if "n_rb" in report:
        print(f"MIB: {report['n_rb']} RB ({ {6: 1.4, 15: 3, 25: 5, 50: 10, 75: 15, 100: 20}[report['n_rb']]:g} MHz), "
              f"{report['ports']} CRS port(s), {len(report['mibs'])} frame(s) decoded")
    sent = [e for e in report["sib1"] if "dci" in e]
    ok = sum(e["crc"] for e in sent)
    print(f"SIB1: {ok} of {len(sent)} transmissions passed CRC24A on their own"
          + (f"; {sum(c['crc'] for c in report['combined'])} of {len(report['combined'])} combined periods"
             if report["combined"] else ""))
    fields = report.get("sib1_fields")
    if not fields:
        return
    if "plmns" not in fields:
        print(f"  {fields}")
        return
    for p in fields["plmns"]:
        print(f"  PLMN {p['mcc'] or '(same MCC)'}-{p['mnc']}")
    print(f"  tracking area code {fields['tracking_area_code']} (0x{fields['tracking_area_code']:04X})")
    print(f"  cell identity {fields['cell_identity']} = eNB {fields['enb_id']} cell {fields['cell_in_enb']}")
    print(f"  band {fields['freq_band_indicator']}" + ("  (64 can mean the band is in multiBandInfoList)"
                                                       if fields["freq_band_indicator"] == 64 else ""))
    print(f"  q-RxLevMin {fields['q_rx_lev_min_dbm']} dBm"
          + (f", p-Max {fields['p_max_dbm']} dBm" if "p_max_dbm" in fields else "")
          + f", barred {fields['cell_barred']}")
    bits = np.asarray(report["sib1_bits"], np.uint8)
    print(f"  SIB1 ({len(bits)} bits): " + np.packbits(bits).tobytes().hex())


def save_llrs(path: Path, report: dict) -> None:
    """Per transmission: the descrambled LLRs the turbo chain received, and its settings."""
    sent = [e for e in report["sib1"] if "llr" in e]
    np.savez_compressed(path, **{f"llr_{i}": e["llr"] for i, e in enumerate(sent)},
                        sfn=[e["sfn"] for e in sent], rv=[e["rv"] for e in sent],
                        G=[e["G"] for e in sent], tbs=[e["grant"]["tbs"] for e in sent],
                        crc=[e["crc"] for e in sent], pci=report["cell"].pci)
    print(f"LLRs of {len(sent)} SIB1 transmissions: {path} (LLR = log P(0)/P(1), after descrambling)")


SELFTESTS = [
    dict(name="5 MHz, 2 ports, 1A localized", n_rb=25, ports=2, fs=7.68e6),
    dict(name="10 MHz, 4 ports, 1A distributed gap 2", n_rb=50, ports=4, fs=15.36e6,
         distributed=True, gap2=True, vrb_start=2, n_vrb=4, cfi=3, phich_res=2),
    dict(name="1.4 MHz, 1 port, 1C", n_rb=6, ports=1, fs=1.92e6, fmt="1C", vrb_start=0, n_vrb=4,
         mcs=3, cfi=2, aggregation=4, candidate=0),
    dict(name="20 MHz, 2 ports, 1C gap 1, extended PHICH", n_rb=100, ports=2, fs=23.04e6, fmt="1C",
         vrb_start=8, n_vrb=8, mcs=10, cfi=3, phich_dur=1, phich_res=3),
    dict(name="15 MHz, 1 port, 1A distributed", n_rb=75, ports=1, fs=23.04e6, distributed=True,
         vrb_start=10, n_vrb=6, mcs=9, n1a=2),
    dict(name="3 MHz, 2 ports, 1A localized", n_rb=15, ports=2, fs=3.84e6, vrb_start=5, n_vrb=5, mcs=4),
]


def selftest(seed: int) -> int:
    rng = np.random.default_rng(seed)
    failures = 0
    for case in SELFTESTS:
        case = dict(case)
        name, fs = case.pop("name"), case.pop("fs")
        cfg = lte_dl.TxConfig(pci=int(rng.integers(504)), sfn0=int(rng.integers(1024)), **case)
        cfo, ppm = float(rng.uniform(-45e3, 45e3)), float(rng.uniform(-20, 20))
        x, truth = lte_dl.transmit(cfg, fs, 9, rng, snr_db=12, cfo=cfo, ppm=ppm,
                                   lead=int(rng.integers(0, int(fs * 7e-3))))
        started = time.monotonic()
        report = lte_dl.receive(x, fs, log=lambda *_: None)
        sent = [e for e in report["sib1"] if "dci" in e]
        good = [e for e in sent if e["crc"] and np.array_equal(e["bits"], truth["payload"])]
        checks = dict(pci=report["cell"].pci == cfg.pci, n_rb=report.get("n_rb") == cfg.n_rb,
                      ports=report.get("ports") == cfg.ports,
                      sib1=bool(sent) and len(good) == len(sent),
                      fields=report.get("sib1_fields", {}).get("cell_identity") == cfg.cell_identity)
        ok = all(checks.values())
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: PCI {report['cell'].pci}/{cfg.pci}, "
              f"CFO {report['cell'].cfo:+.0f}/{cfo:+.0f} Hz, SIB1 {len(good)}/{len(sent)} exact, "
              f"{time.monotonic() - started:.1f}s" + ("" if ok else f"  {checks}"))
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freq", type=float, help="downlink carrier frequency in Hz (capture)")
    ap.add_argument("--rate", type=float, default=23.04e6, help="sample rate (default 23.04e6)")
    ap.add_argument("--ms", type=float, default=100, help="capture length in ms (default 100)")
    ap.add_argument("--gain", type=float, help="manual RX gain in dB (default: slow AGC)")
    ap.add_argument("--uri", default="ip:192.168.2.1", help="libiio URI (default ip:192.168.2.1)")
    ap.add_argument("--save", type=Path, help="write the capture to this .npz")
    ap.add_argument("--load", type=Path, help="decode a saved .npz, .cf32 or .cs16 capture")
    ap.add_argument("--llr", type=Path, help="write each SIB1 transmission's LLRs to this .npz")
    ap.add_argument("--max-cfo", type=float, default=60e3, help="CFO search range in Hz (default 60e3)")
    ap.add_argument("--exact", action="store_true", help="exact log-MAP turbo decoding (default max-log)")
    ap.add_argument("--selftest", action="store_true", help="decode synthetic cells and check the results")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    lte_dl.turbo_core.approx_star = not args.exact
    if args.selftest:
        return selftest(args.seed)
    if args.load:
        x, fs, freq = load(args.load, args.rate if args.load.suffix != ".npz" else None)
        freq = args.freq or freq
    else:
        if not args.freq:
            ap.error("--freq (or --load) is required")
        fs, freq = args.rate, args.freq
        x = capture(args.uri, freq, fs, int(fs * args.ms / 1e3), args.gain)
        if args.save:
            np.savez_compressed(args.save, x=x, fs=fs, freq=freq)
            print(f"capture: {args.save}")
    report = lte_dl.receive(x, fs, max_cfo=args.max_cfo)
    show(report, freq)
    if args.llr:
        save_llrs(args.llr, report)
    return 0 if report.get("sib1_bits") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
