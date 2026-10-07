"""RX transaction scenarios and measurements, separate from the hardware oracle."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "python"))
from turbo_3gpp import core, turbo_encoding_chain
from turbo_3gpp._qpp import QPP
from rx_reference import DEFAULTS, FIELDS, Receiver, configuration, make_frame
import rx_phy

# Es/N0 in dB. "awgn" rises with modulation order so every Q_m sees some
# coded errors; "fade" is a deep fade for HARQ soft combining.
SNR_DB = {"clean": 30, "fade": -8, "adc-clipping": 30, "cfo-edge": 30}
AWGN_SNR_DB = {1: 1, 2: 4, 4: 10, 6: 16, 8: 22, 10: 28}


N_MAX = 65536


def cases(full=True):
    """A deterministic coverage schedule; payloads/noise come from the caller RNG."""
    result = []

    def add(name, A=40, G=None, channel="clean", payload=None, **settings):
        settings.setdefault("pid", 0 if settings.get("I_HARQ") else 7)
        C = len(core.get_3gpp_code_block_segment_lengths(A + 24))
        # Large payloads do not fit N samples as BPSK at SPS=2; send QPSK.
        if "Q_m" not in settings and rx_phy.SPS * 4 * (A + 24) * 33 / 32 + rx_phy.SEARCH + 400 > N_MAX:
            settings["Q_m"] = 2
        unit = C * settings.get("Q_m", 1) * settings.get("N_L", 1)
        G = int(np.ceil((G if G is not None else 4 * (A + 24)) / unit) * unit)
        result.append(dict(name=name, config=dict(DEFAULTS, A=A, G=G, **settings),
                           channel=channel, payload=payload or name))

    # Keep the default sim.py ten frames diverse, including interleaved state.
    add("clean")
    add("noisy", A=128, channel="awgn", approximate=0)
    add("harq-0-fade", A=128, G=160, channel="fade", payload="harq-0", I_HARQ=1)
    add("harq-1-start", A=40, payload="harq-1", pid=1, I_HARQ=1)
    add("harq-0-combine", A=128, G=608, payload="harq-0", I_HARQ=1, new_data=0, rv_idx=2)
    add("harq-1-combine", A=40, payload="harq-1", pid=1, I_HARQ=1, new_data=0, rv_idx=3, Q_m=4, N_L=2)
    add("harq-0-new-data", A=17, I_HARQ=1)
    add("two-code-blocks", A=6121, approximate=0)
    add("limited-buffer", A=128, G=160, I_LBRM=1, N_IR=192, rv_idx=1)
    add("zero-iterations", A=40, iterations_x2=0)
    add("three-code-blocks", A=12217)
    add("half-iteration", A=128, iterations_x2=1)
    add("adc-clipping", channel="adc-clipping")
    add("cfo-edge", channel="cfo-edge")
    add("faded-codeword", channel="fade")
    add("harq-0-after-reset", A=17, payload="harq-0-new-data", I_HARQ=1, new_data=0, rv_idx=1)
    add("harq-disabled-discards-state", A=128, pid=0)
    add("harq-reenabled", A=40, I_HARQ=1)
    add("empty-reception", G=0)
    if full:
        for i, K in enumerate(sorted(QPP)):
            add(f"qpp-{K}", A=K - 24, approximate=i % 2, rv_idx=i % 4)
        for A in (1, 15, 17, 487, 488, 489, 999, 1000, 1001, 2023, 2024, 2025,
                  6119, 6120, 6121, 12215, 12216, 12217):
            add(f"boundary-{A}", A=A)
        for rv in range(4):
            for qm in (1, 2, 4, 6, 8, 10):
                for nl in (1, 2, 4):
                    add(f"rate-rv{rv}-qm{qm}-nl{nl}", G=(96, 192, 384)[rv % 3],
                        rv_idx=rv, Q_m=qm, N_L=nl, approximate=rv % 2,
                        I_LBRM=rv % 2, N_IR=96 if rv % 2 else 0, channel="awgn")
        for mode in (0, 1):
            for count in (0, 1, 2, 3, 4, 8, 16):
                add(f"iterations-{count}-mode-{mode}", A=128, G=192,
                    iterations_x2=count, approximate=mode, channel="awgn")
        add("segmented-limited-harq-start", A=6121, G=12000, N_IR=20000,
            I_LBRM=1, I_HARQ=1, pid=2, payload="segmented", channel="fade")
        add("segmented-limited-harq-combine", A=6121, G=25000, N_IR=20000,
            I_LBRM=1, I_HARQ=1, pid=2, payload="segmented", new_data=0, rv_idx=2)
    return result


def transactions(scenarios, rng, n):
    payloads = {}
    for case in scenarios:
        v = case["config"]
        key = case["payload"]
        if key not in payloads:
            payloads[key] = rng.integers(0, 2, v["A"])
        payload = payloads[key]
        encoded = turbo_encoding_chain(**configuration(v))(payload)
        if len(encoded) != v["G"]:
            raise ValueError(f"{case['name']}: encoder did not produce G bits")
        channel = case["channel"]
        snr = AWGN_SNR_DB[v["Q_m"]] if channel == "awgn" else SNR_DB[channel]
        iq = rx_phy.transmit(encoded, v["Q_m"], n, rng, snr,
                            rms=1800 if channel == "adc-clipping" else None,
                            cfo=rng.choice((-.95, .95)) * np.pi / 16 if channel == "cfo-edge" else None)
        frame = make_frame(n, iq, **v)
        # Nonzero control padding catches designs that read past the header.
        frame[len(FIELDS):, 2] = rng.integers(-16, 17, n - len(FIELDS))
        yield case, frame, payload


def clean_frame(n, rng, **settings):
    """A valid high-SNR frame carrying the all-zero codeword, for protocol checks."""
    v = dict(DEFAULTS, **settings)
    return make_frame(n, rx_phy.transmit(np.zeros(v["G"]), v["Q_m"], n, rng, 30), **settings)


def check_protocol(n, processes):
    """Contract checks, including invalid headers and state lifecycle."""
    receiver = Receiver(n, processes)
    rng = np.random.default_rng(0)
    frame = clean_frame(n, rng)
    checks = 0
    for key, value in (("version", 2), ("A", n+1), ("G", n+1), ("rv_idx", 4),
                       ("Q_m", 3), ("N_L", 0), ("N_IR", -1), ("iterations_x2", -1),
                       ("approximate", 2), ("pid", processes), ("new_data", 0)):
        bad = frame.copy()
        bad[FIELDS.index(key), 2] = value
        try:
            receiver.process(bad)
        except ValueError:
            checks += 1
        else:
            raise AssertionError(f"invalid {key} accepted")
    for value in (np.nan, np.inf, 0.5):
        bad = frame.copy()
        bad[0, 2] = value
        try:
            receiver.process(bad)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("invalid header accepted")
    expected = receiver.process(frame)
    padded = frame.copy()
    padded[len(FIELDS):, 2] = np.inf
    np.testing.assert_array_equal(receiver.process(padded.ravel()), expected)
    checks += 1
    bad = frame.copy()
    bad[n - 1, 0] = np.nan
    try:
        receiver.process(bad)
    except ValueError:
        checks += 1
    else:
        raise AssertionError("non-finite IQ sample accepted")
    # The upstream G-prime/transposition quirk is rejected, not silently fixed.
    bad = frame.copy()
    bad[FIELDS.index("G"), 2], bad[FIELDS.index("Q_m"), 2] = 191, 2
    try:
        receiver.process(bad)
    except ValueError:
        checks += 1
    else:
        raise AssertionError("inconsistent rate matching accepted")
    start = clean_frame(n, rng, I_HARQ=1)
    receiver.process(start)
    continuation = start.copy()
    continuation[FIELDS.index("new_data"), 2] = 0
    changed = continuation.copy()
    changed[FIELDS.index("A"), 2] = 41
    try:
        receiver.process(changed)
    except ValueError:
        checks += 1
    else:
        raise AssertionError("structural change retained HARQ context")
    receiver.reset()
    try:
        receiver.process(continuation)
    except ValueError:
        checks += 1
    else:
        raise AssertionError("reset retained HARQ context")
    return checks


def octave_compare(records):
    """Replay the exact active LLRs/configs through the original MATLAB chain."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "python" / "tests"))
    from oracle import Oracle, cell
    headers = np.array([[record[0]["config"][key] for key in FIELDS] for record in records])
    llrs = cell([record[1] for record in records])
    # Explicit lifecycle calls are the existing test adapter's substitute for
    # MATLAB System objects. Codec algorithm bodies remain unchanged.
    script = '''
contexts=cell(1, max(headers(:,12))+1);
decoded=cell(1,size(headers,1)); iterations=decoded;
for j=1:size(headers,1)
 h=headers(j,:); nir=h(7); if nir==0, nir=Inf; end
 pid=h(12)+1; approx_star=logical(h(11));
 if h(9) && ~h(13)
  d=contexts{pid}; d.G=h(3); d.rv_idx=h(4); d.Q_m=h(5); d.N_L=h(6);
  d.iterations=h(10)/2; d.processTunedPropertiesImpl();
 else
  d=turbo_decoding_chain('A',h(2),'G',h(3),'rv_idx',h(4),'Q_m',h(5),...
   'N_L',h(6),'N_IR',nir,'I_LBRM',h(8),'I_HARQ',h(9),'iterations',h(10)/2);
  d.setupImpl(); contexts{pid}=[];
 end
 [decoded{j}, iterations{j}]=d.stepImpl(llrs{j});
 if h(9), contexts{pid}=d; end
end
'''
    oracle = Oracle()
    try:
        decoded, iterations = oracle.run(script, dict(headers=headers, llrs=llrs), ["decoded", "iterations"])
        for index, (_, _, bits, used) in enumerate(records):
            np.testing.assert_array_equal(bits, decoded[0, index].ravel())
            np.testing.assert_array_equal(used, iterations[0, index].ravel())
    finally:
        oracle.directory.cleanup()
    return len(records)


def run(n, processes):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("quick", "full"), default="full")
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--report", type=Path, default=Path("/tmp/turbo-rx-report.json"))
    parser.add_argument("--octave", action="store_true", help="also compare every selected transaction with original MATLAB in Octave")
    args = parser.parse_args()
    started = time.monotonic()
    receiver = Receiver(n, processes)
    rows, records = [], []
    quick_count = len(cases(False))
    previous_mode = core.approx_star
    for index, (case, frame, payload) in enumerate(transactions(cases(args.suite == "full"), np.random.default_rng(args.seed), n)):
        tick = time.monotonic()
        out = receiver.process(frame)
        assert core.approx_star == previous_mode, "decoder mode leaked outside transaction"
        valid, length, blocks, pid, rv = map(int, out[:5, 1])
        bits = out[:length, 0]
        used = out[:blocks, 2]
        assert out.shape == (n, 3) and np.all(np.isfinite(out))
        assert pid == case["config"]["pid"] and rv == case["config"]["rv_idx"]
        assert length == (len(payload) if valid else 0)
        assert np.all(out[length:, 0] == 0) and np.all(out[5:, 1] == 0) and np.all(out[blocks:, 2] == 0)
        assert np.all((bits == 0) | (bits == 1))
        assert np.all((used >= 0) & (used <= case["config"]["iterations_x2"] / 2))
        errors = int(np.count_nonzero(bits != payload)) if valid else None
        # CRC rejection/noisy recovery is a measurement, not a performance gate.
        # Exact clean recovery checks below are algorithmic identity checks.
        if case["name"] in ("clean", "two-code-blocks", "three-code-blocks", "harq-0-combine", "harq-0-new-data") or case["name"].startswith(("qpp-", "boundary-")):
            np.testing.assert_array_equal(bits, payload, err_msg=case["name"])
        rows.append(dict(name=case["name"], config=case["config"], channel=case["channel"],
                         code_block_lengths=core.get_3gpp_code_block_segment_lengths(len(payload)+24).tolist(),
                         crc_valid=bool(valid), decoded_length=length, bit_errors=errors,
                         ber=errors / len(payload) if valid else None, iterations=used.tolist(),
                         elapsed_seconds=time.monotonic()-tick))
        if args.octave:
            records.append((case, receiver.unpack(frame)[1], bits.copy(), used.copy()))
    protocol_checks = check_protocol(n, processes)
    comparisons = 0
    if args.octave:
        # Keep the interleaved quick HARQ sequence in one Octave process. The
        # rest are independent packets except the final segmented HARQ pair.
        # Bound each batch to stay within the adapter's per-call timeout.
        comparisons += octave_compare(records[:quick_count])
        offset = quick_count
        while offset < len(records):
            end = min(offset + 24, len(records))
            while end < len(records) and not records[end][0]["config"]["new_data"]:
                end += 1
            comparisons += octave_compare(records[offset:end])
            offset = end
    report = dict(suite=args.suite, seed=args.seed, frame_capacity=n, harq_processes=processes,
                  transactions=len(rows), qpp_lengths_covered=sorted({k for row in rows for k in row["code_block_lengths"]}),
                  protocol_checks=protocol_checks, octave_transactions=comparisons,
                  elapsed_seconds=time.monotonic()-started, results=rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Measured {len(rows)} RX transactions, {len(report['qpp_lengths_covered'])} QPP sizes; "
          f"{comparisons} MATLAB comparisons; {protocol_checks} protocol checks.")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    # The windowed single-burst front end, independent of main.py's stream N.
    raise SystemExit(run(N_MAX, 8))
