"""Tool catalog exposed to the LLM.

Each tool is a `Tool` object with:
  - `schema`: Anthropic tool schema (sent to the API)
  - `handler`: callable invoked when the model calls the tool

Tools are constructed against a `ToolContext` which carries the active
project, buildspace root, and a `ProjectPaths` resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .editor import build_editor_tool
from .sim import build_run_sim_tool
from .pnr import build_run_pnr_tool
from .reports import build_read_report_tool
from .python_ref import build_run_python_ref_tool


@dataclass
class Tool:
    """A single tool exposed to the LLM."""

    schema: dict
    handler: Callable[[dict], Any]

    @property
    def name(self) -> str:
        return self.schema["name"]


@dataclass
class ToolContext:
    """Shared state the tool handlers need."""

    project_dir: Path
    build_dir: Path
    reference_py: Path
    hw_yaml: dict
    project_yaml: dict


def build_default_toolset(ctx: ToolContext, *, model: str | None = None) -> list[Tool]:
    """Standard tool catalog for an iterate loop."""
    return [
        build_editor_tool(ctx, model=model),
        build_run_sim_tool(ctx),
        build_run_pnr_tool(ctx),
        build_read_report_tool(ctx),
        build_run_python_ref_tool(ctx),
    ]
