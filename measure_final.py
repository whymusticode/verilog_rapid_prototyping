#!/usr/bin/env python3
"""Independently measure completed batch RTL with original references and routed timing."""
import argparse
import json
from pathlib import Path

import codex_run
import evald


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    for conversion in sorted(args.batch.resolve().glob("conversion_*")):
        run = conversion / "run.json"
        if not run.exists():
            continue
        saved = json.loads(run.read_text())
        # The original project is recorded with every evaluation.
        import yaml
        info = yaml.safe_load((args.batch / "model_info.yaml").read_text())
        project = Path(info["projects"][int(conversion.name.split("_")[-1])])
        usage = codex_run.Usage(0, [1, 5, .1])
        usage.value = {k: saved[k] for k in ("input_tokens", "cached_input_tokens", "output_tokens", "weighted_tokens")}
        recorder = evald.Recorder(project, conversion / "rtl", usage)
        # Original sim also regenerates IO/tb.sv, which synthesis elaborates from.
        sim = recorder.evaluate("sim", [], "original")
        hardware = recorder.evaluate("synth", ["--implement", "--paths", "3"], "original")
        last = recorder.evaluate("sim", ["--drain-stall", "20"], "original")
        report = {"sim": sim["record"], "routed": hardware["record"], "backpressure": last["record"]}
        (conversion / "final_measurements.json").write_text(json.dumps(report, indent=2) + "\n")
        print(project.name, {"simulation_exit": sim["exit"], "routed_exit": hardware["exit"],
                             "backpressure_exit": last["exit"],
                             "fmax_mhz": hardware["record"].get("fmax_mhz")}, flush=True)


if __name__ == "__main__":
    main()
