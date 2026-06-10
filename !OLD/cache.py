"""Deterministic on-disk cache helpers for py2v."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cache_root() -> Path:
    configured = os.environ.get("PY2V_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / ".py2v_cache"


def llm_cache_dir() -> Path:
    return cache_root() / "llm"


def vivado_cache_dir() -> Path:
    return cache_root() / "vivado"


def canonical_json(value: Any) -> str:
    """Serialize deterministically for hash keying."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(payload: Any, *, namespace: str) -> str:
    body = canonical_json(payload)
    digest = hashlib.sha256()
    digest.update(f"{namespace}\n".encode("utf-8"))
    digest.update(body.encode("utf-8"))
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        tmp_path.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


@contextlib.contextmanager
def advisory_lock(lock_path: Path) -> Iterator[None]:
    """Cross-process advisory lock; no-op fallback if flock unavailable."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            yield
    finally:
        fh.close()
