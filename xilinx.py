"""Run Xilinx tools (vivado, xvlog, xelab, xsim) jailed to one conversion directory.

Vivado's Tcl can `exec` anything and write anywhere, so the agent's own
commands cannot be made safe by checking their arguments. Instead every such
process runs under bubblewrap with the conversion directory as its only
writable path, the toolchain read-only, the rest of the home directory absent,
and no network.  The Vivado FHS environment is itself a bubblewrap container;
it nests inside this one.
"""

from __future__ import annotations

import getpass
import os
import shlex
import shutil
import subprocess
from pathlib import Path

# Pinned so measurements stay comparable between runs; see synth.VIVADO_VERSION.
VIVADO_VERSION = os.environ.get("VIVADO_VERSION", "2023.2")
PLUTO = Path("/home/work/Projects/pluto")
FHS_FLAKE = PLUTO / "nix" / "vivado-fhs"
SETUP = PLUTO / "scripts" / "use-vivado"
XILINX_ROOT = PLUTO.parent / ".xilinx"
# The same system paths the agent sandbox reads, plus the toolchain.
JAIL_READ = ("/nix/store", "/run/current-system", "/bin", "/usr",
             "/etc/passwd", "/etc/group", "/etc/hosts", "/etc/resolv.conf",
             "/etc/nsswitch.conf", "/etc/localtime", "/etc/ssl",
             "/etc/static", "/etc/pki", str(XILINX_ROOT), str(SETUP.parent))
JAIL_PATH = "/run/current-system/sw/bin"

_launcher: str | None = None


def launcher() -> str:
    """The FHS environment's entry point, built once instead of `nix run` per job."""
    global _launcher
    if _launcher is None:
        built = subprocess.run(["nix", "build", f"path:{FHS_FLAKE}#vivado-fhs",
                                "--no-link", "--print-out-paths"],
                               text=True, capture_output=True)
        if built.returncode:
            raise RuntimeError(f"cannot build the Vivado environment: {built.stderr.strip()}")
        store = Path(built.stdout.split()[-1])
        programs = sorted((store / "bin").iterdir())
        if len(programs) != 1:
            raise RuntimeError(f"expected one launcher in {store / 'bin'}, found {programs}")
        _launcher = str(programs[0])
    return _launcher


def command(script: str, cwd: Path, writable: list[Path], readable: list[Path] = ()) -> list[str]:
    """Return argv that runs the bash ``script`` with Vivado's tools on PATH.

    ``cwd`` must lie inside one of ``writable``.  The script starts in ``cwd``
    after the toolchain settings are sourced.
    """
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bubblewrap (bwrap) is required to run Xilinx tools")
    home = writable[0] / ".xilinx_home"
    home.mkdir(parents=True, exist_ok=True)
    user = getpass.getuser()
    argv = [bwrap, "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
            "--new-session", "--clearenv",
            "--setenv", "HOME", str(home), "--setenv", "USER", user,
            "--setenv", "LOGNAME", user, "--setenv", "PATH", JAIL_PATH,
            "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for path in dict.fromkeys([*JAIL_READ, *map(str, readable)]):
        if os.path.exists(path):
            argv.extend(("--ro-bind", path, path))
    for path in writable:
        argv.extend(("--bind", str(path), str(path)))
    argv.extend(("--remount-ro", "/", "--chdir", str(cwd), "--"))
    inner = (f"source {shlex.quote(str(SETUP))} {shlex.quote(VIVADO_VERSION)} >/dev/null || exit 2; "
             f"cd {shlex.quote(str(cwd))} || exit 2; {script}")
    niceness = [tool for tool in (shutil.which("ionice"),) if tool]
    prefix = [niceness[0], "-c", "3"] if niceness else []
    if nice := shutil.which("nice"):
        prefix += [nice, "-n", "19"]
    return [*prefix, *argv, launcher(), "-lc", inner]
