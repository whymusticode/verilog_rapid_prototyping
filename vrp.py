"""Shared helpers for the rapid-prototyping command line tools."""

from __future__ import annotations

import importlib.util
import inspect
import math
import re
import sys
from dataclasses import dataclass
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
    if not callable(getattr(module, "target", None)) and not callable(getattr(module, "generate", None)):
        raise ValueError(f"{path} must define generate(samples) or target(x)")
    return module


@dataclass
class Stream:
    """A project's whole input and expected output as flat scalar streams.

    x holds input scalars, in_lanes per input sample (complex: real, imag).
    y holds expected output scalars, out_lanes per output element. ready[i] is
    the number of input samples after which y[i] is determined. Formats are
    (bits, frac, signed) per scalar. groups partition y into measurement masks.
    frame is N for framed (legacy target/stream) projects, else None.
    """
    x: np.ndarray
    in_lanes: int
    y: np.ndarray
    out_lanes: int
    ready: np.ndarray
    in_format: tuple[int, int, bool]
    out_format: tuple[int, int, bool]
    groups: dict[str, np.ndarray]
    primary: str
    frame: int | None = None

    @property
    def samples(self) -> int:
        return len(self.x) // self.in_lanes


def element_format(spec: dict[str, Any]) -> tuple[int, int, bool]:
    return int(spec["bits"]), int(spec.get("frac", 0)), bool(spec.get("signed", True))


def flat(value: Any) -> tuple[np.ndarray, int]:
    """Scalars of a sample sequence and the scalars per sample (complex -> 2)."""
    value = np.asarray(value)
    per = (2 if np.iscomplexobj(value) else 1) * (int(np.prod(value.shape[1:])) if value.ndim > 1 else 1)
    return lanes(value), per


def load_stream(module: ModuleType, params: dict[str, Any], samples: int, rng) -> Stream:
    """The stream sim measures: at least `samples` input samples when possible."""
    if callable(getattr(module, "generate", None)):
        # A generate() that takes rng draws its stimulus from sim's seeded generator.
        seeded = "rng" in inspect.signature(module.generate).parameters
        result = module.generate(samples, rng=rng) if seeded else module.generate(samples)
        x, in_lanes = flat(result["x"])
        y, out_lanes = flat(result["y"])
        ready = np.repeat(np.asarray(result["ready"], dtype=np.int64), out_lanes)
        groups = {name: np.asarray(mask, dtype=bool).ravel()
                  for name, mask in (result.get("groups") or {"all": np.ones(len(y), dtype=bool)}).items()}
        coverage = sum(mask.astype(int) for mask in groups.values())
        if any(mask.size != y.size for mask in groups.values()) or np.any(coverage != 1):
            raise ValueError("measurement groups must partition every output value exactly once")
        primary = result.get("primary", "all" if "all" in groups else next(iter(groups)))
        return Stream(x, in_lanes, y, out_lanes, ready, element_format(params["input"]),
                      element_format(params["output"]), groups, primary)
    # Framed projects: frames of N samples streamed back to back, each frame's
    # output determined once that frame has arrived.
    count = int(params.get("N", 1))
    frames = max(1, -(-samples // count))
    inputs, expected = framed(module, rng, count, frames)
    in_scalars = [lanes(v) for v in inputs]
    if any(len(v) != len(in_scalars[0]) or len(v) % count for v in in_scalars):
        raise ValueError("input frames must contain the same multiple of N values every frame")
    x, in_lanes = np.concatenate(in_scalars), len(in_scalars[0]) // count
    out_scalars = [lanes(v) for v in expected]
    if any(len(v) != len(out_scalars[0]) or len(v) % count for v in out_scalars):
        raise ValueError("target output must contain the same multiple of N values every frame")
    y = np.concatenate(out_scalars)
    per_frame = len(out_scalars[0])
    ready = np.repeat((np.arange(frames) + 1) * count, per_frame)
    primary, masks = measurement_masks(module, expected)
    width = int(params.get("bits", 16))
    frac = fraction_bits([x, y], width)
    return Stream(x, in_lanes, y, per_frame // count, ready, (width, frac, True), (width, frac, True),
                  masks, primary, frame=count)


def framed(module: ModuleType, rng, count: int, frames: int):
    """Input frames and reference frames from target/stream/inputs."""
    readings = getattr(module, "_vrp_readings", [])
    if readings:
        if len(readings) < frames:
            raise ValueError(f"main.py made {len(readings)} target readings, {frames} frames needed")
        return [x for x, _ in readings[:frames]], [y for _, y in readings[:frames]]
    if (stimulus := getattr(module, "inputs", None)) is not None:
        inputs = [np.asarray(v) for v in stimulus(rng, frames)]
        if len(inputs) != frames:
            raise ValueError(f"inputs(rng, count) returned {len(inputs)} vectors, expected {frames}")
    else:
        inputs = [rng.uniform(-1, 1, count) for _ in range(frames)]
    # A design that carries state between frames cannot be modelled by
    # resetting the reference for every frame; ``stream`` describes the whole
    # back-to-back sequence.
    if (streamer := getattr(module, "stream", None)) is not None:
        expected = [np.asarray(y) for y in streamer(inputs)]
        if len(expected) != frames:
            raise ValueError(f"stream(frames) returned {len(expected)} frames, expected {frames}")
        return inputs, expected
    return inputs, [np.asarray(module.target(v)) for v in inputs]


def measurement_masks(module, expected) -> tuple[str, dict[str, np.ndarray]]:
    """A framed project's measurement_groups hook, concatenated over frames."""
    hook = getattr(module, "measurement_groups", None)
    groups = hook(expected) if hook else {"all": [np.ones(lanes(v).size, dtype=bool) for v in expected]}
    primary = getattr(module, "measurement_primary", "all")
    if primary not in groups:
        raise ValueError("measurement_primary must name an output group")
    masks = {name: np.concatenate([np.asarray(m, dtype=bool).ravel() for m in frame_masks])
             for name, frame_masks in groups.items()}
    if np.any(sum(m.astype(int) for m in masks.values()) != 1):
        raise ValueError("measurement groups must partition every output value exactly once")
    return primary, masks


def measure(stream: Stream, actual: np.ndarray, count: int) -> dict[str, dict]:
    """Per-group error statistics over the first `count` output scalars."""
    want, got = stream.y[:count], np.asarray(actual, dtype=float)[:count]
    if not np.all(np.isfinite(got)):
        raise ValueError("non-finite output cannot be measured")
    measured = {}
    for name, mask in stream.groups.items():
        w, g = want[mask[:count]], got[mask[:count]]
        error = g - w
        rmse = float(np.sqrt(np.mean(error ** 2))) if w.size else None
        peak = float(np.max(np.abs(w))) if w.size else None
        precision = (None if not w.size else float("inf") if rmse == 0
                     else float(np.log2(peak / rmse)) if peak else float("-inf"))
        measured[name] = dict(samples=int(w.size), mismatches=int(np.count_nonzero(error)),
                              rmse=rmse, precision_bits=precision, peak=peak)
    return measured


def quantize_format(values: np.ndarray, fmt: tuple[int, int, bool]) -> np.ndarray:
    width, frac, signed = fmt
    scaled = np.rint(np.asarray(values, dtype=float) * (1 << frac)).astype(object)
    low, high = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
    bad = [v for v in scaled if v < low or v > high]
    if bad:
        raise ValueError(f"{len(bad)} values do not fit {width}-bit {'signed' if signed else 'unsigned'} "
                         f"FRAC={frac} (e.g. {bad[0] / (1 << frac)})")
    return scaled


def unpack(text: str, count: int, fmt: tuple[int, int, bool]) -> list[float]:
    width, frac, signed = fmt
    packed, mask = int(text, 16), (1 << width) - 1
    result = []
    for index in range(count):
        value = (packed >> (index * width)) & mask
        if signed and value >> (width - 1):
            value -= 1 << width
        result.append(value / (1 << frac))
    return result


ASSIGN_RE = re.compile(r"(?:\bparameter\b\s*)?(?:(?:integer|int|logic|bit|signed|unsigned)\s+)*"
                       r"(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)\s*=\s*(.+)", re.S)


def split_top(text: str) -> list[str]:
    """Split on commas outside parentheses/brackets/braces."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += char in "([{"
        depth -= char in ")]}"
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return parts + [current]


def top_parameters(files: list[Path], top: str) -> dict[str, str]:
    """Header and body `parameter` defaults of the top module (unevaluated text)."""
    for path in files:
        text = re.sub(r"//.*?$|/\*.*?\*/", "", path.read_text(), flags=re.M | re.S)
        match = re.search(rf"\bmodule\s+{re.escape(top)}\b\s*", text)
        if not match:
            continue
        result, rest = {}, text[match.end():]
        if rest.startswith("#"):
            open_at = rest.index("(")
            depth = 0
            for index in range(open_at, len(rest)):
                depth += rest[index] == "("
                depth -= rest[index] == ")"
                if depth == 0:
                    break
            for item in split_top(rest[open_at + 1:index]):
                found = ASSIGN_RE.fullmatch(item.strip())
                if found:
                    result[found.group(1)] = found.group(2).strip()
            rest = rest[index + 1:]
        body = rest[:rest.find("endmodule")] if "endmodule" in rest else rest
        for statement in re.findall(r"\bparameter\b([^;]*);", body):
            for item in split_top(statement):
                found = ASSIGN_RE.fullmatch(item.strip())
                if found:
                    result[found.group(1)] = found.group(2).strip()
        return result
    return {}


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
    # A peak just below a power of two leaves integer_bits one too low, and
    # rounding then lands one step past full scale. Give back a bit when it does.
    while frac > 0 and round(peak * (1 << frac)) > (1 << (width - 1)) - 1:
        frac -= 1
    if frac < 0:
        raise ValueError(f"{width} bits cannot represent observed magnitude {peak:g}")
    return frac


def lanes(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value)
    if np.iscomplexobj(value):
        return np.column_stack((value.real.ravel(), value.imag.ravel())).ravel()
    return value.astype(float).ravel()


def pack_hex(values: np.ndarray, width: int) -> str:
    mask = (1 << width) - 1
    packed = 0
    for index, value in enumerate(values):
        packed |= (int(value) & mask) << (index * width)
    digits = math.ceil(len(values) * width / 4)
    return f"{packed:0{digits}x}"
