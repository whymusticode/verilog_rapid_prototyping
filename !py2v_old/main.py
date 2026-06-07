#!/usr/bin/env python3
"""py2v CLI entry point.

Subcommands:
  extract <project>            PDF -> reference.py + py2c.yaml + reference_bugs.md
  rtl     <project>            First-draft HLS C++ generation
  sim     <project>            Run HLS C-sim against Python reference
  pnr     <project>            Run HLS csynth estimate
  iterate <project>            Iterative loop (correctness | speed)
  hw      list | show <name>   Inspect hardware presets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_extract(args: argparse.Namespace) -> None:
    from py2v.extract import extract

    spec = Path(args.spec) if args.spec else None
    result = extract(Path(args.project), spec_path=spec)
    _print_json(result)


def cmd_rtl(args: argparse.Namespace) -> None:
    from py2v.rtl import generate_rtl

    result = generate_rtl(
        Path(args.project),
        max_rounds=args.max_rounds,
        budget_usd=args.budget_usd,
    )
    _print_json(result)


def cmd_sim(args: argparse.Namespace) -> None:
    from py2v.project import load_project
    from py2v.tools import ToolContext
    from py2v.tools.sim import build_run_sim_tool

    proj = load_project(Path(args.project))
    ctx = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    tool = build_run_sim_tool(ctx)
    result = tool.handler(
        {
            "tolerance_lsb": args.tolerance_lsb,
        }
    )
    _print_json(result)
    sys.exit(0 if result.get("pass") else 1)


def cmd_pnr(args: argparse.Namespace) -> None:
    from py2v.project import load_project
    from py2v.tools import ToolContext
    from py2v.tools.pnr import build_run_pnr_tool

    proj = load_project(Path(args.project))
    ctx = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    tool = build_run_pnr_tool(ctx)
    result = tool.handler(
        {"phase": args.phase, "clock_mhz": args.clock_mhz, "top": args.top}
    )
    _print_json(result)
    sys.exit(0 if result.get("pass") else 1)


def cmd_python_ref(args: argparse.Namespace) -> None:
    from py2v.project import load_project
    from py2v.tools import ToolContext
    from py2v.tools.python_ref import build_run_python_ref_tool

    proj = load_project(Path(args.project))
    ctx = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    tool = build_run_python_ref_tool(ctx)
    result = tool.handler(
        {
            k: v
            for k, v in {
                "seed": args.seed,
                "n": args.n,
                "max_iter": args.max_iter,
            }.items()
            if v is not None
        }
    )
    _print_json(result)
    sys.exit(0 if "ok" in result else 1)


def cmd_iterate(args: argparse.Namespace) -> None:
    from py2v.iterate import iterate

    result = iterate(
        Path(args.project),
        phase=args.phase,
        max_rounds=args.max_rounds,
        target_cycles=args.target_cycles,
        budget_usd=args.budget_usd,
        relaxed=(not args.strict_target),
        auto_scale=(not args.no_auto_scale),
    )
    _print_json(result)
    sys.exit(0 if (result.get("success") or result.get("best_effort")) else 1)


def cmd_hw(args: argparse.Namespace) -> None:
    from py2v.project import HW_DIR, list_hw_presets, load_hw_preset

    if args.hw_action == "list":
        for name in list_hw_presets():
            preset, _ = load_hw_preset(name)
            part = preset.get("part", "?")
            family = preset.get("family", "?")
            print(f"{name:12s}  part={part:30s}  family={family}")
    elif args.hw_action == "show":
        if not args.name:
            sys.exit("hw show requires <name>")
        _, text = load_hw_preset(args.name)
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="py2v")
    sub = p.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="PDF -> reference.py + py2c.yaml + bugs notes")
    ex.add_argument("project", type=str, help="path to projects/<name>/")
    ex.add_argument("--spec", type=str, default=None, help="explicit PDF path")
    ex.set_defaults(func=cmd_extract)

    rtl = sub.add_parser("rtl", help="generate first-draft HLS C++ + tb")
    rtl.add_argument("project", type=str)
    rtl.add_argument("--max-rounds", type=int, default=30)
    rtl.add_argument("--budget-usd", type=float, default=4.0)
    rtl.set_defaults(func=cmd_rtl)

    sim = sub.add_parser("sim", help="run HLS C-sim against the Python reference")
    sim.add_argument("project", type=str)
    sim.add_argument("--tolerance-lsb", type=int, default=1)
    sim.set_defaults(func=cmd_sim)

    pnr = sub.add_parser("pnr", help="run HLS csynth timing/resource estimate")
    pnr.add_argument("project", type=str)
    pnr.add_argument("--phase", choices=["synth", "impl"], default="synth")
    pnr.add_argument("--clock-mhz", type=float, default=None)
    pnr.add_argument("--top", type=str, default="kernel_top")
    pnr.set_defaults(func=cmd_pnr)

    pyref = sub.add_parser("python-ref", help="run reference.py and emit reference_*.txt")
    pyref.add_argument("project", type=str)
    pyref.add_argument("--seed", type=int, default=None)
    pyref.add_argument("--n", type=int, default=None)
    pyref.add_argument("--max-iter", type=int, default=None)
    pyref.set_defaults(func=cmd_python_ref)

    it = sub.add_parser("iterate", help="LLM iterate loop")
    it.add_argument("project", type=str)
    it.add_argument("--phase", choices=["correctness", "speed"], default="correctness")
    it.add_argument("--max-rounds", type=int, default=15)
    it.add_argument("--target-cycles", type=int, default=None)
    it.add_argument("--budget-usd", type=float, default=8.0)
    it.add_argument(
        "--strict-target",
        action="store_true",
        help="Fail hard unless target criteria are fully met.",
    )
    it.add_argument(
        "--no-auto-scale",
        action="store_true",
        help="Disable automatic fixed-point frac_bits scaling to reduce saturation.",
    )
    it.set_defaults(func=cmd_iterate)

    hw = sub.add_parser("hw", help="hardware preset inspection")
    hw_sub = hw.add_subparsers(dest="hw_action", required=True)
    hw_list = hw_sub.add_parser("list")
    hw_list.set_defaults(func=cmd_hw, hw_action="list", name=None)
    hw_show = hw_sub.add_parser("show")
    hw_show.add_argument("name", type=str)
    hw_show.set_defaults(func=cmd_hw, hw_action="show")
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
