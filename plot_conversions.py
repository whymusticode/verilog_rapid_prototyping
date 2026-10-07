#!/usr/bin/env python3
"""Plot archived conversion measurements against cumulative weighted tokens.

No synthetic score or performance cutoffs: every marker is a recorded evaluator
observation. Source hashes allow matching hardware and numerical measurements.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(batch: Path) -> list[dict]:
    rows = []
    for conversion in sorted(batch.glob("conversion_*")):
        log = conversion / "evald.jsonl"
        if not log.exists():
            continue
        for line in log.read_text().splitlines():
            row = json.loads(line)
            row.update(batch=batch.name, conversion=conversion.name)
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", type=Path, nargs="+")
    parser.add_argument("-o", "--output", type=Path, default=Path("conversion_analysis"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [row for batch in args.batches for row in load(batch)]
    if not rows:
        raise SystemExit("no recorded evaluations")
    (args.output / "measurements.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (args.output / "measurements.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    projects = list(dict.fromkeys(row["project"] for row in rows))
    metrics = [("precision_bits", "Precision bits ↑"),
               ("cycles_per_sample", "Cycles/sample ↓"), ("fmax_mhz", "Fmax MHz ↑"),
               ("lut", "LUTs ↓"), ("dsp", "DSPs ↓"), ("ram", "RAM tiles ↓")]
    fig, axes = plt.subplots(len(projects), len(metrics), figsize=(21, 3.5 * len(projects)), squeeze=False)
    colors = plt.get_cmap("tab10")
    summary = []
    for bi, batch in enumerate(args.batches):
        subset = [r for r in rows if r["batch"] == batch.name]
        for pi, project in enumerate(projects):
            trial = [r for r in subset if r["project"] == project]
            originals = [r for r in trial if r.get("reference") == "original" and r["tool"] == "sim"]
            for mi, (key, title) in enumerate(metrics):
                ax = axes[pi][mi]
                points = [r for r in trial if key in r and r[key] is not None and "weighted_tokens" in r]
                for stage in ("sim", "synthesis_estimate", "routed"):
                    group = [r for r in points if r.get("timing_stage", "sim") == stage]
                    if not group:
                        continue
                    # Dots joined only chronologically; failed measurements remain visible.
                    xs = [r["weighted_tokens"] / 1000 for r in group]
                    ys = [r[key] for r in group]
                    marker = "s" if stage == "routed" else "o"
                    ax.plot(xs, ys, color=colors(bi), alpha=.55, linewidth=1,
                            linestyle="--" if stage == "synthesis_estimate" else "-",
                            label=batch.name + (" routed" if stage == "routed" else ""))
                    for x, y, r in zip(xs, ys, group):
                        measured = r["exit"] == 0
                        ax.scatter(x, y, color=colors(bi), marker=marker if measured else "x", s=30)
                        if r.get("reference") == "original":
                            ax.scatter(x, y, facecolors="none", edgecolors=colors(bi), s=100)
                if mi == 0 and any(r.get("exact") for r in trial):
                    ax.text(.02, .95 - bi * .1, f"{batch.name}: exact result(s)",
                            transform=ax.transAxes, color=colors(bi), fontsize=8, va="top")
                ax.set_title(f"{project} · {title}", fontsize=10)
                ax.set_xlabel("Weighted tokens (thousands)", fontsize=8)
                ax.grid(alpha=.2)
            simulations = [r for r in trial if r["tool"] == "sim" and "precision_bits" in r]
            hardware = [r for r in trial if r["tool"] == "synth" and r["exit"] == 0]
            summary.append({"batch": batch.name, "project": project,
                            "first_simulation": simulations[0] if simulations else None,
                            "final_original": originals[-1] if originals else None,
                            "last_hardware": hardware[-1] if hardware else None})
    handles, labels = [], []
    for ax in axes.flat:
        h, l = ax.get_legend_handles_labels()
        for hi, li in zip(h, l):
            if li not in labels:
                handles.append(hi); labels.append(li)
    fig.legend(handles, labels, loc="upper center", ncol=4, fontsize=9)
    fig.suptitle("Measured conversion progress — × measurement error; ○ original check; square = routed timing\n"
                 "Fresh unseeded stimuli; synthesis estimates are dashed. No aggregate quality score.", y=.965, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .925))
    fig.savefig(args.output / "performance.png", dpi=150)
    fig.savefig(args.output / "performance.svg")
    plt.close(fig)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(args.output / "performance.png")


if __name__ == "__main__":
    main()
