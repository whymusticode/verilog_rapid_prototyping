"""Shared helpers for the rapid-prototyping command line tools."""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import yaml


MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b")


def load_params(reference: Path) -> dict[str, Any]:
    path = reference.with_name("params.yaml")
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_reference(path: Path, params: dict[str, Any]) -> ModuleType:
    """Load a reference file, making YAML parameters available as globals."""
    spec = importlib.util.spec_from_file_location("vrp_reference", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(params)
    readings: list[tuple[np.ndarray, np.ndarray]] = []

    def capture(frame: Any, event: str, arg: Any) -> None:
        if event == "return" and frame.f_code.co_name == "target" and "x" in frame.f_locals:
            readings.append((np.asarray(frame.f_locals["x"]).copy(), np.asarray(arg).copy()))

    previous_profile = sys.getprofile()
    try:
        sys.setprofile(capture)
        spec.loader.exec_module(module)
    finally:
        sys.setprofile(previous_profile)
    module.__dict__["_vrp_readings"] = readings
    if not callable(getattr(module, "target", None)):
        raise ValueError(f"{path} must define target(x)")
    return module


def verilog_files(rtl_dir: Path) -> list[Path]:
    files = sorted(path.resolve() for path in (*rtl_dir.rglob("*.v"), *rtl_dir.rglob("*.sv")))
    if not files:
        raise ValueError(f"no .v or .sv files found below {rtl_dir}")
    return files


def infer_top(files: list[Path], requested: str | None) -> str:
    modules: list[str] = []
    instantiated: set[str] = set()
    for path in files:
        text = re.sub(r"//.*?$|/\*.*?\*/", "", path.read_text(), flags=re.M | re.S)
        modules.extend(MODULE_RE.findall(text))
    for path in files:
        text = path.read_text()
        for name in modules:
            if re.search(rf"\b{re.escape(name)}\s+(?:#\s*\([^;]*?\)\s*)?[A-Za-z_]\w*\s*\(", text, re.S):
                instantiated.add(name)
    if requested:
        if requested not in modules:
            raise ValueError(f"top module {requested!r} was not found")
        return requested
    roots = sorted(set(modules) - instantiated)
    if len(roots) != 1:
        raise ValueError(f"cannot infer top module (candidates: {', '.join(roots) or 'none'}); use --top")
    return roots[0]


def fraction_bits(values: list[np.ndarray], width: int) -> int:
    """Choose the most fractional bits that cannot overflow signed width."""
    peak = max((float(np.max(np.abs(v))) for v in values if v.size), default=0.0)
    integer_bits = 0 if peak == 0 else max(0, math.ceil(math.log2(peak + np.finfo(float).eps)))
    frac = width - 1 - integer_bits
    if frac < 0:
        raise ValueError(f"{width} bits cannot represent observed magnitude {peak:g}")
    return frac


def lanes(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value)
    if np.iscomplexobj(value):
        return np.column_stack((value.real.ravel(), value.imag.ravel())).ravel()
    return value.astype(float).ravel()


def quantize(value: np.ndarray, width: int, frac: int) -> np.ndarray:
    scaled = np.rint(lanes(value) * (1 << frac)).astype(object)
    low, high = -(1 << (width - 1)), (1 << (width - 1)) - 1
    if any(v < low or v > high for v in scaled):
        raise ValueError("fixed-point conversion overflowed; increase bits in params.yaml")
    return np.asarray(scaled, dtype=object)


def pack_hex(values: np.ndarray, width: int) -> str:
    mask = (1 << width) - 1
    packed = 0
    for index, value in enumerate(values):
        packed |= (int(value) & mask) << (index * width)
    digits = math.ceil(len(values) * width / 4)
    return f"{packed:0{digits}x}"


def unpack_signed(text: str, count: int, width: int) -> np.ndarray:
    packed = int(text, 16)
    mask = (1 << width) - 1
    sign = 1 << (width - 1)
    result = []
    for index in range(count):
        value = (packed >> (index * width)) & mask
        result.append(value - (1 << width) if value & sign else value)
    return np.asarray(result, dtype=float)
