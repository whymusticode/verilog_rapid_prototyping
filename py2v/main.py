#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

SKELETON_PATH = Path(__file__).parent / "py2c_skeleton.yaml"

GET_PARAMS_PROMPT = f"""You are helping convert a Python reference design into synthesizable Verilog.
Read the requirements document (may be PDF or plain text) and produce a YAML file matching
the skeleton below EXACTLY — same top-level keys, same nested structure, same order.

Rules:
  - Every key in the skeleton MUST appear in the output.
  - If the document specifies a value, use it.
  - If the document does not specify a value, fall back to the default shown in the skeleton.
  - For every value that came from a default (not the document), append a note to `notes`
    of the form: "defaulted: <dotted.key.path> (document did not specify)".
  - List fields (parameters, inputs, outputs) remain empty lists if the document says nothing.
  - Do not invent signal names, widths, or parameters that aren't in the document.
  - Output ONLY the YAML body — no code fences, no commentary, no leading/trailing text.

Skeleton:
{SKELETON_PATH.read_text()}"""


def cmd_get_params(input_path: Path) -> None:
    input_path = input_path.resolve()
    if not input_path.exists():
        sys.exit(f"input not found: {input_path}")

    out = input_path.parent / "py2c.yaml"
    prompt = (
        f"{GET_PARAMS_PROMPT}\n\n"
        f"Read the requirements document at: {input_path}\n"
        f"Write the resulting YAML to: {out}\n"
        f"Do not print the YAML to stdout. When finished, print only the single word DONE."
    )

    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--add-dir", str(input_path.parent),
            "--permission-mode", "acceptEdits",
            "--allowed-tools", "Read,Write",
        ],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)
    if not out.exists():
        sys.exit("claude finished but py2c.yaml was not written")
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--mode", required=True, choices=["get_params"])
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    if args.mode == "get_params":
        cmd_get_params(args.input)


if __name__ == "__main__":
    main()
