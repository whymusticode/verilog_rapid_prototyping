"""PDF -> reference.py + py2c.yaml + reference_bugs.md.

Three independent API calls, each scoped to a single output. We rely on
prompt caching of the (large) PDF block so the per-call cost is dominated
by output tokens.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import yaml

from .client import (
    Client,
    cached,
    doc_pdf_b64,
    doc_text,
    strip_code_fences,
    text,
)


SKELETON_PATH = Path(__file__).parent / "skeletons" / "py2c.yaml"

VERBATIM_INSTRUCTION = """You are extracting source code from a technical document.
Locate every Python code block in the attached PDF (formatted code, listings,
appendices, inline snippets). Concatenate them in document order into a single
Python module.

Rules:
  - Preserve identifiers, indentation, comments, and ordering exactly.
  - Do not "fix" obvious bugs.
  - If multiple unrelated programs appear, separate them with a comment line
    `# --- next snippet (page <N>) ---`.
  - If a snippet looks truncated or unreadable, insert a comment
    `# TODO: extraction-uncertain (page <N>): <one-line reason>` and emit the
    best-effort transcription.
  - Do not add any imports, helper functions, or wrappers that are not in the
    document.
  - Output ONLY the Python source - no markdown fences, no commentary."""

BUG_REVIEW_INSTRUCTION = """You are reviewing the attached PDF's Python reference for
likely numerical or algorithmic issues. Do NOT modify the code. Output a
Markdown bullet list, one issue per bullet, in the form:

  - **<short title>** (`<file>:<line range>`): <what's wrong>; <suggested fix or check>

If the document is internally consistent and no issues are found, output the
single line: `No issues found.`"""


def _py2c_instruction(skeleton_text: str) -> str:
    return (
        "You are helping convert a Python reference design into synthesizable Verilog.\n"
        "Read the attached requirements document and produce a YAML file matching\n"
        "the skeleton below EXACTLY - same top-level keys, same nested structure,\n"
        "same order.\n\n"
        "Rules:\n"
        "  - Every key in the skeleton MUST appear in the output.\n"
        "  - If the document specifies a value, use it.\n"
        "  - If the document does not specify a value, fall back to the default shown.\n"
        "  - For every value that came from a default (not the document), append a\n"
        "    note to `notes` of the form:\n"
        "    \"defaulted: <dotted.key.path> (document did not specify)\".\n"
        "  - List fields (parameters, inputs, outputs) remain empty lists if the\n"
        "    document says nothing.\n"
        "  - Do not invent signal names, widths, or parameters that aren't in the\n"
        "    document.\n"
        "  - Output ONLY the YAML body - no code fences, no commentary.\n\n"
        f"Skeleton:\n{skeleton_text}"
    )


def _build_pdf_block(input_path: Path) -> dict:
    suffix = input_path.suffix.lower()
    data = input_path.read_bytes()
    if suffix == ".pdf":
        b64 = base64.standard_b64encode(data).decode("ascii")
        block = doc_pdf_b64(b64)
    else:
        block = doc_text(data.decode("utf-8", errors="replace"))
    block["cache_control"] = {"type": "ephemeral"}
    return block


def extract(project_dir: Path, *, spec_path: Path | None = None) -> dict:
    """Run the three extraction calls; write outputs into `project_dir`.

    Returns a small dict with paths to the written files and total cost.
    """
    project_dir = project_dir.resolve()
    if spec_path is None:
        candidates = sorted(project_dir.glob("*.pdf"))
        if not candidates:
            sys.exit(f"no PDF found in {project_dir}; pass --spec PATH")
        spec_path = candidates[0]
    spec_path = spec_path.resolve()
    if not spec_path.exists():
        sys.exit(f"spec not found: {spec_path}")

    client = Client()
    pdf_block = _build_pdf_block(spec_path)
    skeleton = SKELETON_PATH.read_text()

    # Call A: verbatim Python.
    res_a = client.chat(
        messages=[
            {
                "role": "user",
                "content": [pdf_block, text(VERBATIM_INSTRUCTION)],
            }
        ]
    )
    py_text = strip_code_fences(res_a.text)
    if not py_text:
        sys.exit("verbatim extraction returned empty text")
    reference_py = project_dir / "reference.py"
    reference_py.write_text(py_text + ("\n" if not py_text.endswith("\n") else ""))

    # Call B: bug review (also reuses the cached PDF).
    res_b = client.chat(
        messages=[
            {
                "role": "user",
                "content": [pdf_block, text(BUG_REVIEW_INSTRUCTION)],
            }
        ]
    )
    bugs_md = res_b.text.strip() or "No issues found."
    bugs_path = project_dir / "reference_bugs.md"
    bugs_path.write_text("# Reference bug review\n\n" + bugs_md + "\n")

    # Call C: py2c.yaml fill.
    res_c = client.chat(
        messages=[
            {
                "role": "user",
                "content": [pdf_block, text(_py2c_instruction(skeleton))],
            }
        ]
    )
    yaml_text = strip_code_fences(res_c.text)
    if not yaml_text:
        sys.exit("py2c extraction returned empty text")
    py2c_path = project_dir / "py2c.yaml"
    py2c_path.write_text(yaml_text + ("\n" if not yaml_text.endswith("\n") else ""))

    # If no project.yaml exists, synthesize one. We override the skeleton's
    # default fixed-point with whatever py2c.yaml extracted from the PDF, so
    # the reference outputs don't immediately saturate.
    project_yaml_path = project_dir / "project.yaml"
    if not project_yaml_path.exists():
        skel_proj_path = Path(__file__).parent / "skeletons" / "project.yaml"
        proj_doc = yaml.safe_load(skel_proj_path.read_text()) or {}
        try:
            py2c_doc = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError:
            py2c_doc = {}
        py2c_fp = py2c_doc.get("fixed_point") if isinstance(py2c_doc, dict) else None
        if isinstance(py2c_fp, dict):
            proj_doc["fixed_point"] = {
                "total_bits": int(py2c_fp.get("total_bits", proj_doc["fixed_point"]["total_bits"])),
                "frac_bits": int(py2c_fp.get("frac_bits", proj_doc["fixed_point"]["frac_bits"])),
            }
        project_yaml_path.write_text(yaml.safe_dump(proj_doc, sort_keys=False))

    return {
        "reference_py": str(reference_py),
        "reference_bugs_md": str(bugs_path),
        "py2c_yaml": str(py2c_path),
        "project_yaml": str(project_yaml_path),
        "estimated_cost_usd": round(client.usage.estimate_cost_usd(client.model), 4),
        "usage": {
            "input_tokens": client.usage.input_tokens,
            "output_tokens": client.usage.output_tokens,
            "cache_creation": client.usage.cache_creation_input_tokens,
            "cache_read": client.usage.cache_read_input_tokens,
        },
    }
