"""Thin wrapper around the vivado invocation so callers don't care whether
vivado is running natively, under flatpak, or inside a docker container.

Backend is picked from the VIVADO_BACKEND env var (see .envrc.default).
If unset / set to "auto", we try native → flatpak → docker in that order.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

NATIVE_BIN = os.environ.get("VIVADO_NATIVE_BIN", "vivado")
FLATPAK_APP = os.environ.get("VIVADO_FLATPAK_APP", "com.github.corna.Vivado")
DOCKER_IMAGE = os.environ.get("VIVADO_DOCKER_IMAGE", "vivado:latest")
DOCKER_BIN = os.environ.get("VIVADO_DOCKER_BIN", "/opt/Xilinx/Vivado/2024.1/bin/vivado")
DOCKER_PLATFORM = os.environ.get("VIVADO_DOCKER_PLATFORM", "").strip()

_BACKENDS = ("native", "flatpak", "docker")


def detect_backend() -> str:
    forced = os.environ.get("VIVADO_BACKEND", "").strip().lower()
    if forced and forced != "auto":
        if forced not in _BACKENDS:
            raise RuntimeError(
                f"VIVADO_BACKEND={forced!r} is not one of {_BACKENDS}"
            )
        return forced

    if shutil.which(NATIVE_BIN):
        return "native"
    if sys.platform.startswith("linux") and shutil.which("flatpak"):
        r = subprocess.run(
            ["flatpak", "info", FLATPAK_APP],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return "flatpak"
    if shutil.which("docker"):
        return "docker"
    raise RuntimeError(
        "could not auto-detect a vivado backend; "
        "set VIVADO_BACKEND to one of: native, flatpak, docker"
    )


def _docker_mount_path(path: Path, mount_root: Path) -> str:
    """Translate a host path into the /workspace path inside the docker container."""
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(mount_root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"docker backend: {resolved} must be under the mount root {mount_root}"
        ) from exc
    return f"/workspace/{rel}" if str(rel) != "." else "/workspace"


def _build_cmd(
    backend: str,
    vivado_args: Sequence[str],
    mount_root: Path,
) -> list[str]:
    if backend == "native":
        return [NATIVE_BIN, *vivado_args]
    if backend == "flatpak":
        return ["flatpak", "run", FLATPAK_APP, *vivado_args]
    if backend == "docker":
        cmd = [
            "docker", "run", "--rm",
        ]
        if DOCKER_PLATFORM:
            cmd += ["--platform", DOCKER_PLATFORM]
        cmd += [
            "-v", f"{mount_root.resolve()}:/workspace",
            "-w", "/workspace",
            DOCKER_IMAGE,
            DOCKER_BIN,
            *vivado_args,
        ]
        return cmd
    raise ValueError(f"unknown backend: {backend}")


def _build_exec_cmd(
    backend: str,
    exec_args: Sequence[str],
    mount_root: Path,
) -> list[str]:
    """Build a backend-specific command for a generic executable (not vivado)."""
    if backend == "native":
        return list(exec_args)
    if backend == "flatpak":
        return ["flatpak", "run", FLATPAK_APP, *exec_args]
    if backend == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
        ]
        if DOCKER_PLATFORM:
            cmd += ["--platform", DOCKER_PLATFORM]
        cmd += [
            "-v",
            f"{mount_root.resolve()}:/workspace",
            "-w",
            "/workspace",
            DOCKER_IMAGE,
            *exec_args,
        ]
        return cmd
    raise ValueError(f"unknown backend: {backend}")


def run(
    args: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Invoke vivado with the given CLI args.

    `cwd` is used both as the subprocess working directory and (for the docker
    backend) as the directory bind-mounted to /workspace.
    """
    backend = detect_backend()
    cwd = Path(cwd or Path.cwd())
    cmd = _build_cmd(backend, list(args), cwd)
    return subprocess.run(cmd, cwd=cwd, check=check)


def run_exec(
    args: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Invoke an arbitrary command in the configured backend context.

    Useful for calling shell scripts that in turn invoke xvlog/xelab/xsim.
    For docker, this runs inside the configured image with `cwd` mounted to
    /workspace.
    """
    backend = detect_backend()
    cwd = Path(cwd or Path.cwd())
    cmd = _build_exec_cmd(backend, list(args), cwd)
    return subprocess.run(cmd, cwd=cwd, check=check)


def run_tcl(
    script: Path | str,
    tclargs: Optional[Sequence[str]] = None,
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run `vivado -mode tcl -source <script> [-tclargs ...]`.

    For the docker backend, the script (and anything it touches) must live
    inside `cwd`, since `cwd` is the only directory mounted into the container.
    """
    script_path = Path(script)
    if not script_path.exists():
        raise FileNotFoundError(f"tcl script not found: {script_path}")

    backend = detect_backend()
    mount_root = Path(cwd or script_path.parent)

    if backend == "docker":
        script_arg = _docker_mount_path(script_path, mount_root)
    else:
        script_arg = str(script_path.resolve())

    vivado_args = ["-mode", "tcl", "-source", script_arg]
    if tclargs:
        vivado_args += ["-tclargs", *map(str, tclargs)]

    return run(vivado_args, cwd=mount_root, check=check)


def backend_identity() -> dict[str, str]:
    """Stable backend/toolchain identity for cache fingerprinting."""
    backend = detect_backend()
    identity = {"backend": backend}
    if backend == "native":
        identity["binary"] = NATIVE_BIN
    elif backend == "flatpak":
        identity["app"] = FLATPAK_APP
    elif backend == "docker":
        identity["image"] = DOCKER_IMAGE
        identity["binary"] = DOCKER_BIN
    return identity


if __name__ == "__main__":
    print(f"vivado backend: {detect_backend()}")
