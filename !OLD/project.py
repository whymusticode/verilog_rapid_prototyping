"""Project + hw-preset loader.

Centralizes the path conventions in one place so subcommands (extract, rtl,
sim, pnr, iterate) all agree on where files live.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

PY2V_ROOT = Path(__file__).parent
HW_DIR = PY2V_ROOT / "hw"
SKELETONS_DIR = PY2V_ROOT / "skeletons"


@dataclass
class Project:
    dir: Path
    project: dict
    project_text: str
    hw: dict
    hw_text: str
    hw_name: str
    py2c: dict
    py2c_text: str
    reference_py: Path

    @property
    def build_dir(self) -> Path:
        return self.dir / "build"

    @property
    def spec_pdf(self) -> Path | None:
        candidates = sorted(self.dir.glob("*.pdf"))
        return candidates[0] if candidates else None


def load_hw_preset(name: str) -> tuple[dict, str]:
    path = HW_DIR / f"{name}.yaml"
    if not path.exists():
        sys.exit(f"unknown hw preset: {name} (looked in {HW_DIR})")
    text = path.read_text()
    return yaml.safe_load(text), text


def list_hw_presets() -> list[str]:
    return sorted(p.stem for p in HW_DIR.glob("*.yaml"))


def load_project(project_dir: Path) -> Project:
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        sys.exit(f"project dir not found: {project_dir}")

    project_yaml_path = project_dir / "project.yaml"
    if not project_yaml_path.exists():
        sys.exit(
            f"missing {project_yaml_path}; run `py2v extract {project_dir}` first "
            f"or copy {SKELETONS_DIR / 'project.yaml'}."
        )
    project_text = project_yaml_path.read_text()
    project = yaml.safe_load(project_text)

    hw_name = project.get("hw")
    if not hw_name:
        sys.exit(f"{project_yaml_path}: missing `hw:` field")
    hw, hw_text = load_hw_preset(hw_name)

    py2c_path = project_dir / "py2c.yaml"
    if not py2c_path.exists():
        sys.exit(
            f"missing {py2c_path}; run `py2v extract {project_dir}` first."
        )
    py2c_text = py2c_path.read_text()
    py2c = yaml.safe_load(py2c_text)

    reference_py = project_dir / "reference.py"
    if not reference_py.exists():
        sys.exit(
            f"missing {reference_py}; run `py2v extract {project_dir}` first."
        )

    return Project(
        dir=project_dir,
        project=project,
        project_text=project_text,
        hw=hw,
        hw_text=hw_text,
        hw_name=hw_name,
        py2c=py2c,
        py2c_text=py2c_text,
        reference_py=reference_py,
    )
