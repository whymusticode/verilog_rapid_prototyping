"""Two-phase iterate loop: correctness then speed."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

import yaml

from .agent import run_agent
from .client import Client, cached
from .project import Project, load_project
from .tools import ToolContext, build_default_toolset
from .tools.python_ref import build_run_python_ref_tool

PROMPTS_DIR = Path(__file__).parent / "prompts"
CORRECTNESS_PROMPT = PROMPTS_DIR / "iterate_correctness.md"
SPEED_PROMPT = PROMPTS_DIR / "iterate_speed.md"


def iterate(
    project_dir: Path,
    *,
    phase: str = "correctness",
    max_rounds: int = 15,
    target_cycles: Optional[int] = None,
    budget_usd: float = 8.0,
    relaxed: bool = True,
    auto_scale: bool = True,
) -> dict:
    proj = load_project(project_dir)
    if target_cycles is None:
        target_cycles = int(proj.project.get("target_cycles", 200))

    scale_info = None
    if auto_scale:
        scale_info = _auto_scale_fixed_point(proj)

    client = Client()
    ctx = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    proj.build_dir.mkdir(parents=True, exist_ok=True)

    tools = build_default_toolset(ctx, model=client.model)

    if phase == "correctness":
        prompt_text = CORRECTNESS_PROMPT.read_text()
        success_check = _correctness_success
        # Correctness phase is sim-only by design: no synth/impl timing checks.
        tools = [t for t in tools if t.name != "run_pnr"]
        seed = (
            "Make `run_sim` pass against the Python reference at integer-LSB "
            "tolerance. Start by calling `run_sim` with default args. "
            "Sandbox note: str_replace tool paths must be relative to build root "
            "(`.`, `hls/`, `sim/`, `reports/`)."
        )
        transcript = proj.build_dir / "transcript_iterate_correctness.jsonl"
    elif phase == "speed":
        prompt_text = SPEED_PROMPT.read_text()
        success_check = _make_speed_success(target_cycles)
        seed = (
            f"The correctness phase is complete. Reduce measured `cycles` per "
            f"decomposition to <= {target_cycles}, while keeping `run_sim` passing "
            f"and `run_pnr` meeting target clock. Start by establishing the current baseline "
            "with `run_sim` then `run_pnr` (impl). Sandbox note: use only build-root "
            "relative paths for editor tool calls (`.`, `hls/`, `sim/`, `reports/`)."
        )
        transcript = proj.build_dir / "transcript_iterate_speed.jsonl"
    else:
        raise ValueError(f"unknown phase: {phase}")

    system_prompt = [
        cached(prompt_text),
        cached(_context_block(proj, target_cycles)),
    ]

    run = run_agent(
        client=client,
        system_prompt=system_prompt,
        seed_user_message=seed,
        tools=tools,
        transcript_path=transcript,
        max_rounds=max_rounds,
        token_budget_usd=budget_usd,
        success_check=success_check,
        stuck_signature=_stuck_sig,
    )
    progress = _extract_progress(transcript)
    best_effort = False
    if not run.success and relaxed and run.stop_reason is not None:
        if run.stop_reason.code in {"max_rounds", "stuck", "token_budget", "end_turn"}:
            best_effort = True

    summary = {
        "phase": phase,
        "stop_reason": run.stop_reason.code if run.stop_reason else None,
        "stop_detail": run.stop_reason.detail if run.stop_reason else "",
        "rounds": run.rounds,
        "success": run.success,
        "best_effort": best_effort,
        "relaxed": relaxed,
        "auto_scale": auto_scale,
        "scale_info": scale_info,
        "progress": progress,
        "transcript": str(transcript),
        "estimated_cost_usd": round(client.usage.estimate_cost_usd(client.model), 4),
    }
    (proj.build_dir / f"iterate_{phase}_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    return summary


def _context_block(proj: Project, target_cycles: int) -> str:
    parts = [
        "## Project context\n",
        "### Sandbox\n"
        "Editor tool is scoped to `projects/<name>/build/`.\n"
        "Use relative paths only: `.`, `hls/`, `sim/`, `reports/`.\n",
        f"### project.yaml\n```yaml\n{proj.project_text}\n```\n",
        f"### hw.yaml ({proj.hw_name})\n```yaml\n{proj.hw_text}\n```\n",
        f"### py2c.yaml\n```yaml\n{proj.py2c_text}\n```\n",
        f"### Target cycles per decomposition: {target_cycles}\n",
        f"### reference.py\n```python\n{proj.reference_py.read_text()}\n```\n",
    ]
    bugs = proj.dir / "reference_bugs.md"
    if bugs.exists():
        parts.append(f"### reference_bugs.md\n{bugs.read_text()}\n")
    return "\n".join(parts)


def _correctness_success(_chat, results: dict) -> bool:
    sim = results.get("run_sim")
    if isinstance(sim, dict) and sim.get("pass") is True:
        return True
    return False


def _make_speed_success(target_cycles: int):
    def check(_chat, results: dict) -> bool:
        sim = results.get("run_sim") or {}
        pnr = results.get("run_pnr") or {}
        if not (isinstance(sim, dict) and isinstance(pnr, dict)):
            return False
        cycles = sim.get("cycles")
        fmax = pnr.get("fmax_mhz")
        req_clk = pnr.get("clock_mhz")
        if not sim.get("pass"):
            return False
        if fmax is None or req_clk is None or fmax < req_clk:
            return False
        if cycles is None or cycles > target_cycles:
            return False
        return True
    return check


def _stuck_sig(results: dict) -> str:
    sim = results.get("run_sim") or {}
    pnr = results.get("run_pnr") or {}
    return (
        f"sim_pass={sim.get('pass')}|"
        f"sim_n_mis={sim.get('n_mismatched')}|"
        f"sim_max_err={sim.get('max_abs_err_lsb')}|"
        f"pnr_fmax={pnr.get('fmax_mhz')}|"
        f"pnr_cycles={sim.get('cycles')}"
    )


def _auto_scale_fixed_point(proj: Project) -> dict:
    """Adjust frac_bits to reduce saturation in generated reference files.

    We keep total_bits fixed and search downward from current frac_bits for the
    highest Q that keeps saturation ratio under threshold.
    """
    fixed = proj.project.get("fixed_point", {})
    total_bits = int(fixed.get("total_bits", 23))
    start_q = int(fixed.get("frac_bits", 20))
    sat_threshold = 0.01

    best_q = start_q
    best_ratio = 1.0

    for q in range(start_q, -1, -1):
        trial_project = copy.deepcopy(proj.project)
        trial_project.setdefault("fixed_point", {})
        trial_project["fixed_point"]["total_bits"] = total_bits
        trial_project["fixed_point"]["frac_bits"] = q
        ctx = ToolContext(
            project_dir=proj.dir,
            build_dir=proj.build_dir,
            reference_py=proj.reference_py,
            hw_yaml=proj.hw,
            project_yaml=trial_project,
        )
        tool = build_run_python_ref_tool(ctx)
        result = tool.handler({})
        if "ok" not in result:
            return {
                "updated": False,
                "error": "run_python_ref failed during auto-scale",
                "detail": result,
            }
        sat_ratio = _saturation_ratio(
            proj.dir / "reference_inputs.txt",
            proj.dir / "reference_eigenvalues.txt",
            total_bits=total_bits,
        )
        best_q = q
        best_ratio = sat_ratio
        if sat_ratio <= sat_threshold:
            break

    updated = best_q != start_q
    if updated:
        proj.project.setdefault("fixed_point", {})
        proj.project["fixed_point"]["total_bits"] = total_bits
        proj.project["fixed_point"]["frac_bits"] = best_q
        _save_project_yaml(proj)
    # Ensure files match the selected Q.
    ctx_final = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    build_run_python_ref_tool(ctx_final).handler({})
    return {
        "updated": updated,
        "total_bits": total_bits,
        "frac_bits_before": start_q,
        "frac_bits_after": best_q,
        "saturation_ratio_after": round(best_ratio, 6),
        "threshold": sat_threshold,
    }


def _saturation_ratio(inputs_path: Path, diag_path: Path, *, total_bits: int) -> float:
    sat_max = (1 << (total_bits - 1)) - 1
    sat_min = -(1 << (total_bits - 1))

    vals: list[int] = []
    for path in (inputs_path, diag_path):
        if not path.exists():
            continue
        for line in path.read_text(errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                vals.append(int(parts[0]))
                vals.append(int(parts[1]))
            except ValueError:
                continue
    if not vals:
        return 0.0
    saturated = sum(1 for v in vals if v == sat_max or v == sat_min)
    return saturated / len(vals)


def _save_project_yaml(proj: Project) -> None:
    fixed = proj.project.get("fixed_point", {})
    test_inputs = proj.project.get("test_inputs", {})
    doc = {
        "hw": proj.project.get("hw", "zu7ev"),
        "target_cycles": int(proj.project.get("target_cycles", 200)),
        "algorithm_family": proj.project.get("algorithm_family", "any"),
        "fixed_point": {
            "total_bits": int(fixed.get("total_bits", 23)),
            "frac_bits": int(fixed.get("frac_bits", 20)),
        },
        "clock_mhz": proj.project.get("clock_mhz"),
        "test_inputs": {
            "count": int(test_inputs.get("count", 1)),
            "seed": int(test_inputs.get("seed", 0)),
        },
    }
    (proj.dir / "project.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    proj.project_text = (proj.dir / "project.yaml").read_text()


def _extract_progress(transcript_path: Path) -> dict:
    best_cycles = None
    best_wns = None
    sim_passes = 0
    pnr_passes = 0
    if not transcript_path.exists():
        return {}
    for line in transcript_path.read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") != "tool_result":
            continue
        tool = ev.get("tool")
        result = ev.get("result", {})
        if tool == "run_sim" and isinstance(result, dict):
            if result.get("pass"):
                sim_passes += 1
            c = result.get("cycles")
            if isinstance(c, int):
                best_cycles = c if best_cycles is None else min(best_cycles, c)
        if tool == "run_pnr" and isinstance(result, dict):
            if result.get("pass"):
                pnr_passes += 1
            w = result.get("wns_ns")
            if isinstance(w, (int, float)):
                best_wns = w if best_wns is None else max(best_wns, w)
    return {
        "sim_passes": sim_passes,
        "pnr_passes": pnr_passes,
        "best_cycles": best_cycles,
        "best_wns_ns": best_wns,
    }
