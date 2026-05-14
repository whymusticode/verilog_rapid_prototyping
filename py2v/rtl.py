"""First-draft RTL generation.

Single agent run: model gets the prompt + project context and uses
str_replace_editor to write rtl/* and tb/* into the buildspace.
"""

from __future__ import annotations

from pathlib import Path

from .agent import run_agent
from .client import Client, cached, text
from .project import load_project
from .tools import ToolContext, build_default_toolset

PROMPT_PATH = Path(__file__).parent / "prompts" / "rtl_first_draft.md"


def generate_rtl(project_dir: Path, *, max_rounds: int = 30, budget_usd: float = 4.0) -> dict:
    proj = load_project(project_dir)
    client = Client()

    ctx = ToolContext(
        project_dir=proj.dir,
        build_dir=proj.build_dir,
        reference_py=proj.reference_py,
        hw_yaml=proj.hw,
        project_yaml=proj.project,
    )
    proj.build_dir.mkdir(parents=True, exist_ok=True)
    (proj.build_dir / "rtl").mkdir(exist_ok=True)
    (proj.build_dir / "tb").mkdir(exist_ok=True)

    tools = build_default_toolset(ctx, model=client.model)
    system_prompt = [
        cached(PROMPT_PATH.read_text()),
        cached(_context_block(proj)),
    ]

    seed = (
        "Generate the first-draft RTL for this project per the system prompt. "
        "Use str_replace_editor to create files under rtl/ and tb/. "
        "Sandbox note: use build-root relative paths (`.`, `rtl/`, `tb/`, `sim/`, `reports/`). "
        "When you've written everything required, end the turn."
    )

    transcript = proj.build_dir / "transcript_rtl.jsonl"
    run = run_agent(
        client=client,
        system_prompt=system_prompt,
        seed_user_message=seed,
        tools=tools,
        transcript_path=transcript,
        max_rounds=max_rounds,
        token_budget_usd=budget_usd,
    )
    return {
        "stop_reason": run.stop_reason.code if run.stop_reason else None,
        "rounds": run.rounds,
        "transcript": str(transcript),
        "estimated_cost_usd": round(client.usage.estimate_cost_usd(client.model), 4),
        "rtl_files": sorted(str(p.relative_to(proj.build_dir)) for p in (proj.build_dir / "rtl").glob("*.v")),
        "tb_files": sorted(str(p.relative_to(proj.build_dir)) for p in (proj.build_dir / "tb").glob("*.v")),
    }


def _context_block(proj) -> str:
    parts = [
        "## Project context\n",
        "### Sandbox\n"
        "Editor tool is scoped to `projects/<name>/build/`.\n"
        "Use relative paths only: `.`, `rtl/`, `tb/`, `sim/`, `reports/`.\n",
        f"### project.yaml\n```yaml\n{proj.project_text}\n```\n",
        f"### hw.yaml ({proj.hw_name})\n```yaml\n{proj.hw_text}\n```\n",
        f"### py2c.yaml\n```yaml\n{proj.py2c_text}\n```\n",
        f"### reference.py\n```python\n{proj.reference_py.read_text()}\n```\n",
    ]
    bugs = proj.dir / "reference_bugs.md"
    if bugs.exists():
        parts.append(f"### reference_bugs.md\n{bugs.read_text()}\n")
    return "\n".join(parts)
