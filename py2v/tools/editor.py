"""Anthropic built-in text editor tool, scoped to the buildspace.

The built-in editor is pure model-side; the SDK only provides the schema.
We provide the file-system handler that backs the commands:
  - view <path> [view_range]
  - create <path> file_text
  - str_replace <path> old_str new_str
  - insert <path> insert_line new_str
  - undo_edit <path>     (only on Claude 3.5 / 3.7 era variants)

The exact tool `type` and `name` differ by model. See `editor_spec_for_model`.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_VIEW_LINES = 800
MAX_FILE_BYTES = 256 * 1024


def editor_spec_for_model(model: str) -> dict:
    """Return {type, name} for the right text-editor variant for `model`.

    Override with PY2V_EDITOR_TOOL=type:name if Anthropic ships another version.
    """
    override = os.environ.get("PY2V_EDITOR_TOOL")
    if override and ":" in override:
        t, n = override.split(":", 1)
        return {"type": t.strip(), "name": n.strip()}

    m = model.lower()
    # Claude Sonnet 4.5 and newer Sonnet 4.x / Opus 4.5 use this GA tool.
    # No `undo_edit`; tool name is `str_replace_based_edit_tool`.
    if "sonnet-4-5" in m or "opus-4-5" in m or "sonnet-4-7" in m or "haiku-4-5" in m:
        return {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}
    # Claude Sonnet 4 / Opus 4 (original release): same name, older type.
    if "claude-sonnet-4" in m or "claude-opus-4" in m or "claude-4" in m:
        return {"type": "text_editor_20250429", "name": "str_replace_based_edit_tool"}
    # Claude 3.7 Sonnet (and 3.5 Sonnet (new)): the older str_replace_editor.
    return {"type": "text_editor_20250124", "name": "str_replace_editor"}


def _resolve(root: Path, raw: str) -> Path:
    """Resolve `raw` against `root`, rejecting anything outside the root."""
    if not raw:
        raise ValueError("path is required")
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    root_resolved = root.resolve()
    try:
        p.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError(
            f"path {p} is outside the buildspace {root_resolved}"
        ) from exc
    return p


def build_editor_tool(ctx, *, model: str | None = None):  # ctx: ToolContext
    """Returns a Tool wrapping the Anthropic built-in editor.

    `model` is used to pick the right tool type/name. If None, we use whatever
    Client's DEFAULT_MODEL says.
    """
    from . import Tool
    from ..client import DEFAULT_MODEL

    history: dict[str, list[str]] = defaultdict(list)
    schema = editor_spec_for_model(model or DEFAULT_MODEL)

    def handler(args: dict) -> Any:
        cmd = args.get("command")
        path_str = args.get("path", "")
        try:
            path = _resolve(ctx.build_dir, path_str)
        except (ValueError, PermissionError) as exc:
            return {"error": str(exc)}

        if cmd == "view":
            return _do_view(path, args.get("view_range"))
        if cmd == "create":
            return _do_create(path, args.get("file_text", ""), history, path_str)
        if cmd == "str_replace":
            return _do_str_replace(
                path,
                args.get("old_str", ""),
                args.get("new_str", ""),
                history,
                path_str,
            )
        if cmd == "insert":
            return _do_insert(
                path,
                int(args.get("insert_line", 0)),
                args.get("new_str", ""),
                history,
                path_str,
            )
        if cmd == "undo_edit":
            return _do_undo(path, history, path_str)
        return {"error": f"unknown command: {cmd}"}

    return Tool(schema=schema, handler=handler)


def _do_view(path: Path, view_range) -> dict:
    if path.is_dir():
        entries = []
        for child in sorted(path.iterdir()):
            entries.append(f"{'d' if child.is_dir() else 'f'} {child.name}")
        return {"entries": entries[:200]}
    if not path.exists():
        return {"error": f"file not found: {path}"}
    if path.stat().st_size > MAX_FILE_BYTES:
        return {"error": f"file too large ({path.stat().st_size} bytes); use a view_range"}
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start, end = 1, len(lines)
    if view_range and isinstance(view_range, list) and len(view_range) == 2:
        start = max(1, int(view_range[0]))
        end = int(view_range[1]) if int(view_range[1]) != -1 else len(lines)
        end = min(end, len(lines))
    if end - start + 1 > MAX_VIEW_LINES:
        end = start + MAX_VIEW_LINES - 1
    selected = lines[start - 1 : end]
    numbered = "\n".join(f"{i+start:5d}|{line}" for i, line in enumerate(selected))
    return {"path": str(path), "start": start, "end": end, "content": numbered}


def _do_create(path: Path, content: str, history, key: str) -> dict:
    if path.exists():
        history[key].append(path.read_text(errors="replace"))
    else:
        history[key].append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return {"ok": True, "bytes": len(content)}


def _do_str_replace(path: Path, old: str, new: str, history, key: str) -> dict:
    if not path.exists():
        return {"error": f"file not found: {path}"}
    text = path.read_text(errors="replace")
    count = text.count(old)
    if count == 0:
        return {"error": "old_str not found in file"}
    if count > 1:
        return {
            "error": (
                f"old_str matches {count} locations; provide more context to make it unique"
            )
        }
    history[key].append(text)
    path.write_text(text.replace(old, new, 1))
    return {"ok": True}


def _do_insert(path: Path, line: int, new: str, history, key: str) -> dict:
    if not path.exists():
        return {"error": f"file not found: {path}"}
    text = path.read_text(errors="replace")
    lines = text.splitlines(keepends=True)
    if line < 0 or line > len(lines):
        return {"error": f"insert_line {line} out of range (0..{len(lines)})"}
    history[key].append(text)
    new_block = new if new.endswith("\n") else new + "\n"
    lines.insert(line, new_block)
    path.write_text("".join(lines))
    return {"ok": True}


def _do_undo(path: Path, history, key: str) -> dict:
    if not history[key]:
        return {"error": "no edit history for this file"}
    prev = history[key].pop()
    path.write_text(prev)
    return {"ok": True}
