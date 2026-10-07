#!/usr/bin/env python3
"""Synthesize an RTL directory with Quartus or Vivado and print a compact summary."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from vrp import infer_top, load_params, verilog_files


DEFAULT_TIMEOUT = {"quartus": 20.0, "vivado": 600.0}
DEFAULT_PERIOD_NS = 10.0
# Xilinx part numbers all start with one of these; everything else is Altera.
VIVADO_PREFIXES = ("xc", "xa", "xq", "xck")
# Vivado often only exists inside a container or module-file environment.  These
# defaults match the Pluto firmware tree; $VIVADO_SHELL and $VIVADO_SETUP
# override them, and $VIVADO bypasses them with a directly runnable executable.
VIVADO_SHELL = "/home/work/Projects/pluto/scripts/vivado-shell"
VIVADO_SETUP = "/home/work/Projects/pluto/scripts/use-vivado"
# The setup script selects one of several installed toolchains, so the version
# is pinned rather than discovered: synthesis results are only comparable
# between runs of the same Vivado.  $VIVADO_VERSION overrides it.
VIVADO_VERSION = "2023.2"


def find(pattern: str, text: str, default: str = "unknown") -> str:
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else default


def utilization(used: str, available: str) -> str:
    """Format a resource as ``used available percent`` when both are known."""
    if used == "unknown":
        return used
    if available == "unknown":
        return used
    try:
        percent = 100.0 * int(used.replace(",", "")) / int(available.replace(",", ""))
    except (ValueError, ZeroDivisionError):
        return f"{used} {available}"
    return f"{used} {available} {percent:.1f}%"


def conversion_params(conversion_dir: Path) -> dict:
    reference = conversion_dir / "python" / "main.py"
    return load_params(reference) if reference.is_file() else {}


def choose_tool(requested: str, part: str) -> str:
    if requested != "auto":
        return requested
    return "vivado" if part.lower().startswith(VIVADO_PREFIXES) else "quartus"


def copy_memories(rtl_dir: Path, work: Path) -> None:
    """Put $readmemh images beside the synthesis run directory."""
    for source in rtl_dir.iterdir():
        if source.is_file() and source.suffix.lower() in {".hex", ".mif", ".mem"}:
            shutil.copy2(source, work / source.name)


def run(command: list[str], work: Path, limit: float, label: str,
        started: float, hint: str = "") -> str:
    """Run a synthesis tool under a wall-clock budget and return its output."""
    print(f"{label}: {' '.join(command[:2])} (timeout: {limit:g}s)...",
          file=sys.stderr, flush=True)
    try:
        process = subprocess.Popen(command, cwd=work, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as error:
        raise RuntimeError(f"cannot start {label}: {error}") from error
    try:
        output, _ = process.communicate(timeout=limit)
    except subprocess.TimeoutExpired as timeout_error:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            remaining, _ = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            remaining, _ = process.communicate()
        partial = timeout_error.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        output = partial + (remaining or "")
        (work / f"{label.lower()}.log").write_text(output)
        milestones = [line for line in output.splitlines()
                      if "Running Quartus" in line or "Processing started" in line
                      or "Command:" in line or "Error (" in line
                      or line.startswith("ERROR:") or line.startswith("Phase ")]
        if milestones:
            print("\n".join(milestones[-12:]), file=sys.stderr)
        elapsed = time.perf_counter() - started
        raise RuntimeError(
            f"{label} exceeded the {limit:g}s evaluation limit "
            f"({elapsed:.1f}s); RTL is too expensive to compile"
        )
    (work / f"{label.lower()}.log").write_text(output)
    if process.returncode:
        print("\n".join(output.splitlines()[-40:]), file=sys.stderr)
        if hint and "command not found" in output:
            raise RuntimeError(hint)
        raise RuntimeError(f"{label} compilation failed")
    return output


def quartus(files: list[Path], rtl_dir: Path, work: Path, top: str, part: str,
            period_ns: float, limit: float, started: float,
            paths: int) -> tuple[str, str, str, list[dict], str]:
    lines = ['set_global_assignment -name FAMILY "Cyclone V"',
             f"set_global_assignment -name DEVICE {part}",
             f"set_global_assignment -name TOP_LEVEL_ENTITY {top}",
             'set_global_assignment -name SDC_FILE "rapid.sdc"']
    for source in files:
        # Some generators put localparam declarations in ANSI parameter
        # lists.  Quartus rejects that construct even in SystemVerilog
        # mode, so normalize temporary synthesis copies to parameters.
        copy = work / "rtl" / source.relative_to(rtl_dir)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(source.read_text().replace("localparam", "parameter"))
        lines.append(f'set_global_assignment -name SYSTEMVERILOG_FILE "{copy}"')
    copy_memories(rtl_dir, work)
    (work / "rapid.qsf").write_text("\n".join(lines) + "\n")
    (work / "rapid.qpf").write_text('PROJECT_REVISION = "rapid"\n')
    (work / "rapid.sdc").write_text(
        f"create_clock -name aclk -period {period_ns:.3f} [get_ports aclk]\n")
    run(["quartus_sh", "--flow", "compile", "rapid"], work, limit, "Quartus", started)
    # Older Quartus writes its reports into output_files/; 25.1std leaves them
    # beside the project file.
    summaries = sorted(work.glob("**/rapid.fit.summary"))
    if not summaries:
        raise RuntimeError("Quartus produced no fitter summary")
    fit = summaries[0].read_text(errors="replace")
    reports = "\n".join(path.read_text(errors="replace")
                        for path in sorted(work.glob("**/rapid.*.rpt")))
    # Cyclone V families report ALMs; older families report LUT equivalents.
    return (quartus_resource(fit, r"(?:Total combinational functions|Logic utilization \(in ALMs\))"),
            quartus_resource(fit, r"Total DSP Blocks"),
            quartus_fmax(reports),
            quartus_paths(work, limit, started, paths) if paths else [],
            quartus_resource(fit, r"Total RAM Blocks"))


def quartus_paths(work: Path, limit: float, started: float,
                  paths: int) -> list[dict]:
    """Re-open the compiled design in the timing analyzer for path detail."""
    (work / "paths.tcl").write_text(f"""project_open rapid
create_timing_netlist -model slow
read_sdc
update_timing_netlist
set worst [get_timing_paths -setup -npaths {paths} -detail path_only]
foreach_in_collection path $worst {{
  set from [get_node_info [get_path_info $path -from] -name]
  set to [get_node_info [get_path_info $path -to] -name]
  puts "VRP_PATH [get_path_info $path -slack]\t[get_path_info $path -num_logic_levels]\
\t[get_path_info $path -data_delay]\t-\t$from\t$to"
}}
""")
    output = run(["quartus_sta", "-t", "paths.tcl"], work,
                 max(limit / 2, 30.0), "Quartus timing", started)
    found = []
    for line in output.splitlines():
        if not line.startswith("VRP_PATH "):
            continue
        fields = [field.strip() for field in line[len("VRP_PATH "):].split("\t")]
        if len(fields) != 6:
            continue
        found.append({"slack": fields[0], "levels": fields[1], "logic": fields[2],
                      "route": fields[3], "from": fields[4], "to": fields[5]})
    return found[:paths]


def quartus_fmax(reports: str) -> str:
    """Return the restricted Fmax of the worst timing corner.

    The Fmax summary puts its ``Fmax ; Restricted Fmax`` labels in a header
    row, so the number has to be read out of the data row underneath it.  The
    slowest corner is tabulated first.
    """
    match = re.search(r"^;\s*[\d.]+\s*MHz\s*;\s*([\d.]+\s*MHz)\s*;", reports, re.M)
    return match.group(1).strip() if match else "unknown"


def quartus_resource(fit: str, name: str) -> str:
    """Read a ``used / available ( percent )`` line out of the fitter summary."""
    match = re.search(rf"{name}\s*:\s*([\d,]+|< \d+)\s*(?:/\s*([\d,]+))?", fit, re.I)
    if not match:
        return "unknown"
    return utilization(match.group(1), match.group(2) or "unknown")


def vivado_command(arguments: list[str], work: Path) -> list[str]:
    """Return a full command line for ``vivado <arguments>`` run in ``work``."""
    if override := os.environ.get("VIVADO"):
        return shlex.split(override) + arguments
    if executable := shutil.which("vivado"):
        return [executable, *arguments]
    launcher = Path(os.environ.get("VIVADO_SHELL", VIVADO_SHELL))
    setup = Path(os.environ.get("VIVADO_SETUP", VIVADO_SETUP))
    if not launcher.is_file():
        raise ValueError("vivado was not found: put it on PATH, set $VIVADO to the "
                         "executable, or set $VIVADO_SHELL to a wrapper shell")
    # The wrapper is a container shell, so the tools only exist inside it: the
    # setup script has to be sourced there, and the wrapper picks its own
    # working directory, so the flow has to return to ours.
    script = [f"cd {shlex.quote(str(work))}"]
    if setup.is_file():
        # The setup script needs the version to source, and reports its own
        # error when that one is not installed; stop there rather than falling
        # through to a bare "vivado: command not found".
        version = os.environ.get("VIVADO_VERSION", VIVADO_VERSION)
        script.append(shlex.join(["source", str(setup), version]) + " || exit 2")
    script.append(shlex.join(["exec", "vivado", *arguments]))
    return [str(launcher), "-lc", "; ".join(script)]


def vivado(files: list[Path], rtl_dir: Path, work: Path, top: str, part: str,
           period_ns: float, limit: float, started: float,
           paths: int, implement: bool = False, generics: dict | None = None
           ) -> tuple[str, str, str, list[dict], str]:
    sources = " ".join(shlex.quote(str(path)) for path in files)
    copy_memories(rtl_dir, work)
    for stale in ("post_synth.dcp", "post_route.dcp"):
        (work / stale).unlink(missing_ok=True)
    (work / "rapid.xdc").write_text(
        f"create_clock -name aclk -period {period_ns:.3f} [get_ports aclk]\n")
    # Out-of-context synthesis: no I/O buffers are inserted, so the numbers
    # describe the module itself rather than a pin-limited wrapper.
    generic_arg = " -generic {" + " ".join(f"{k}={v}" for k, v in generics.items()) + "}" if generics else ""
    (work / "rapid.tcl").write_text(f"""set_param general.maxThreads 4
create_project -in_memory -part {part}
read_verilog -sv [list {sources}]
read_xdc rapid.xdc
synth_design -top {top} -part {part} -mode out_of_context{generic_arg}
write_checkpoint -force post_synth.dcp
{"opt_design" if implement else ""}
{"place_design" if implement else ""}
{"phys_opt_design" if implement else ""}
{"route_design" if implement else ""}
{"write_checkpoint -force post_route.dcp" if implement else ""}
report_utilization -file utilization.rpt
report_timing_summary -file timing.rpt
set paths [get_timing_paths -setup -max_paths {max(paths, 1)} -nworst 1]
if {{[llength $paths] > 0}} {{
  puts "VRP_SLACK [get_property SLACK [lindex $paths 0]]"
}}
foreach path $paths {{
  puts "VRP_PATH [get_property SLACK $path]\t[get_property LOGIC_LEVELS $path]\
\t[get_property DATAPATH_LOGIC_DELAY $path]\t[get_property DATAPATH_NET_DELAY $path]\
\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
}}
puts "VRP_DONE"
""")
    output = run(vivado_command(["-nojournal", "-nolog", "-mode", "batch",
                                 "-source", "rapid.tcl"], work),
                 work, limit, "Vivado", started,
                 hint="the Vivado launcher started but no vivado executable was "
                      "reachable through it; set $VIVADO_VERSION to an installed "
                      "toolchain or $VIVADO to the full path")
    if "VRP_DONE" not in output:
        print("\n".join(output.splitlines()[-40:]), file=sys.stderr)
        raise RuntimeError("Vivado synthesis did not finish")
    report = (work / "utilization.rpt").read_text(errors="replace")
    lut = _resource(report, r"(?:CLB|Slice) LUTs\*?")
    dsp = _resource(report, r"DSPs?(?:48[A-Z0-9]*)?")
    ram = _resource(report, r"Block RAM Tile")
    slack = find(r"VRP_SLACK\s+(-?[\d.]+)", output)
    fmax = "unknown"
    if slack != "unknown":
        achieved = period_ns - float(slack)
        fmax = f"{1000.0 / achieved:.1f} MHz" if achieved > 0 else "unbounded"
    critical = []
    for line in output.splitlines():
        if not line.startswith("VRP_PATH "):
            continue
        fields = [field.strip() for field in line[len("VRP_PATH "):].split("\t")]
        if len(fields) != 6:
            continue
        critical.append({"slack": fields[0], "levels": fields[1],
                         "logic": fields[2], "route": fields[3],
                         "from": fields[4], "to": fields[5]})
    return lut, dsp, fmax, critical[:paths], ram


def _resource(report: str, name: str) -> str:
    """Pull ``used`` and ``available`` out of a Vivado utilization table row."""
    for line in report.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        # Columns are Site Type, Used, Fixed, [Prohibited,] Available, Util%.
        # The percentage can read "<0.01", so count in from the right instead.
        if len(cells) < 4 or not re.fullmatch(name, cells[0], re.I):
            continue
        return utilization(cells[1], cells[-2])
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("conversion", type=Path,
                        help="conversion directory containing rtl/ and python/")
    parser.add_argument("--top")
    parser.add_argument("--project", type=Path,
                        help="override parameter project for independent final checks")
    parser.add_argument("--part", help="overrides the part in params.yaml")
    parser.add_argument("--tool", choices=("auto", "quartus", "vivado"), default="auto",
                        help="default: Vivado for Xilinx parts, Quartus otherwise")
    parser.add_argument("--frequency", type=float,
                        help="target clock in Hz (default: target.frequency in params.yaml)")
    parser.add_argument("--timeout", type=float,
                        help="wall-clock budget in seconds")
    parser.add_argument("--paths", type=int, default=0, metavar="COUNT",
                        help="also print the COUNT worst setup paths")
    parser.add_argument("--implement", action="store_true",
                        help="place and route rather than estimate from synthesis "
                             "(Vivado only; slower but reports the real Fmax)")
    parser.add_argument("--work", type=Path, help="retain synthesis scripts, reports and logs here")
    args = parser.parse_args()
    conversion_dir = args.conversion.resolve()
    rtl_dir = conversion_dir / "rtl"
    files = verilog_files(rtl_dir)
    top = infer_top(files, args.top)
    params = load_params(args.project.resolve() / "main.py") if args.project else conversion_params(conversion_dir)
    part = args.part or params.get("part")
    if not part:
        raise ValueError("FPGA part is required: use --part or conversion/python/params.yaml")
    tool = choose_tool(args.tool, part)
    frequency = args.frequency or (params.get("target") or {}).get("frequency")
    period_ns = 1e9 / float(frequency) if frequency else DEFAULT_PERIOD_NS
    limit = args.timeout or DEFAULT_TIMEOUT[tool]
    started = time.perf_counter()
    # Match the elaboration that was actually simulated, not arbitrary RTL defaults.
    tb = conversion_dir / "IO" / "tb.sv"
    generics = {}
    if tb.exists():
        text = tb.read_text()
        # The testbench marks every parameter it overrides on the DUT.
        for key, value in re.findall(r"localparam integer (\w+)\s*=\s*(\d+);\s*// DUT parameter", text):
            generics[key] = int(value)
    if args.work:
        args.work.mkdir(parents=True, exist_ok=True)
    with (contextlib.nullcontext(str(args.work.resolve())) if args.work else
          tempfile.TemporaryDirectory(prefix=f"vrp-{tool}-")) as name:
        work = Path(name)
        if tool == "vivado":
            lut, dsp, fmax, critical, ram = vivado(files, rtl_dir, work, top, part,
                                                  period_ns, limit, started,
                                                  args.paths, args.implement, generics)
        else:
            if args.implement:
                raise ValueError("--implement is only supported for Vivado")
            lut, dsp, fmax, critical, ram = quartus(files, rtl_dir, work, top, part,
                                                   period_ns, limit, started, args.paths)
    elapsed = time.perf_counter() - started
    print(f"evaluation time: {elapsed:.1f}s")
    print(f"tool: {tool} ({part} @ {1000.0 / period_ns:.1f} MHz)")
    print(f"timing stage: {'routed' if args.implement else 'synthesis estimate'}")
    print(f"elaboration: {generics or 'RTL defaults (no prior simulation)'}")
    print(f"LUT: {lut}")
    print(f"DSP: {dsp}")
    print(f"RAM: {ram}")
    print(f"Fmax: {fmax}")
    if args.paths:
        report_paths(critical)
    return 0


def report_paths(critical: list[dict]) -> None:
    """Print the worst setup paths, worst first."""
    if not critical:
        print("critical paths: none reported")
        return
    print(f"critical paths ({len(critical)}, worst first):")
    for index, path in enumerate(critical, 1):
        delay = f"logic {path['logic']}"
        if path["route"] not in {"-", "", "unknown"}:
            delay += f" route {path['route']}"
        print(f"  {index}. slack {path['slack']}ns  levels {path['levels']}  {delay}")
        print(f"     from {shorten(path['from'])}")
        print(f"     to   {shorten(path['to'])}")


def shorten(name: str, limit: int = 96) -> str:
    return name if len(name) <= limit else name[:limit - 3] + "..."



if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"synth.py: {error}", file=sys.stderr)
        raise SystemExit(1)
