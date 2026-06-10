"""Canonical "correct response" examples for every py2v LLM tool call.

`responses` maps each tool's schema `name` to an example of the dict its
handler returns on success (see py2v/tools/*.py). The editor tool is keyed by
its sub-command since each returns a different shape. Run top-to-bottom (or
send to a REPL) to (re)write the golden files under py2v/tests/files/.
"""

import json
from pathlib import Path

FILES = Path(__file__).parent / "files"
FILES.mkdir(parents=True, exist_ok=True)

responses = {
    # py2v/tools/python_ref.py -> _DRIVER stdout
    "run_python_ref": {
        "ok": True,
        "n": 10,
        "max_iter": 1,
        "seed": 0,
        "fixed_point": {"total_bits": 23, "frac_bits": 20},
        "inputs_path": "projects/eigen/reference_inputs.txt",
        "diag_path": "projects/eigen/reference_eigenvalues.txt",
    },
    # py2v/tools/sim.py -> _run_sim summary
    "run_sim": {
        "pass": True,
        "cache_hit": False,
        "tolerance_lsb": 1,
        "n_compared": 10,
        "n_mismatched": 0,
        "max_abs_err_lsb": 0,
        "first_mismatches": [],
        "iter_count": 12,
        "cycles": 48213,
        "log_tail": "INFO: [SIM 211-1] CSim done with 0 errors.",
    },
    # py2v/tools/pnr.py -> _run_pnr summary
    "run_pnr": {
        "pass": True,
        "phase": "synth",
        "mode": "hls_csynth",
        "clock_mhz": 100.0,
        "period_ns": 10.0,
        "wns_ns": None,
        "fmax_mhz": 137.3,
        "latency_cycles": 48213,
        "util": {
            "lut_as_logic": {"used": 8421, "pct": None},
            "block_ram_tile": {"used": 12, "pct": None},
            "dsps": {"used": 64, "pct": None},
        },
        "errors": [],
        "log_tail": "INFO: [HLS 200-111] Finished Command csynth_design.",
    },
    # py2v/tools/reports.py -> read_report handler
    "read_report": {
        "name": "sim_summary",
        "path": "sim/sim_summary.json",
        "total_lines": 11,
        "returned_lines": 11,
        "tail": False,
        "content": '{\n  "pass": true,\n  "n_compared": 10,\n  "n_mismatched": 0\n}',
    },
    # py2v/tools/editor.py -> build_editor_tool handler, one entry per command
    "str_replace_based_edit_tool": {
        "view": {
            "path": "build/eigen/hls/kernel.cpp",
            "start": 1,
            "end": 3,
            "content": "    1|#include \"kernel.h\"\n    2|\n    3|void kernel_top(...) {",
        },
        "view_dir": {"entries": ["d hls", "f kernel.cpp", "f tb.cpp"]},
        "create": {"ok": True, "bytes": 1234},
        "str_replace": {"ok": True},
        "insert": {"ok": True},
        "undo_edit": {"ok": True},
    },
}

for name, resp in responses.items():
    (FILES / f"{name}.json").write_text(json.dumps(resp, indent=2) + "\n")
    print(f"wrote {FILES.name}/{name}.json")
