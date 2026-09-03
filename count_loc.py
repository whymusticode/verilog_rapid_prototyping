#!/usr/bin/env python3
"""Count non-blank lines in selected source files in this repository."""

from pathlib import Path


INCLUDE_EXTENSIONS = {
    ".py",
}

INCLUDE_DIRECTORIES = {
    ".",
}


def count_lines(path: Path) -> int:
    with path.open(encoding="utf-8", errors="ignore") as source_file:
        return sum(1 for line in source_file if line.strip())


def main() -> None:
    root = Path(__file__).resolve().parent
    total = 0

    paths = {
        path
        for directory in INCLUDE_DIRECTORIES
        for path in (root / directory).glob("*")
        if path.is_file() and path.suffix.lower() in INCLUDE_EXTENSIONS
    }

    for path in sorted(paths):
        lines = count_lines(path)
        total += lines
        print(f"{lines:8}  {path.relative_to(root)}")

    print(f"{'-' * 8}  {'-' * 20}")
    print(f"{total:8}  total")


if __name__ == "__main__":
    main()
