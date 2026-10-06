"""Path traversal protection for every repository file access."""

from __future__ import annotations

import os
from pathlib import Path


class PathTraversalError(PermissionError):
    pass


def safe_join(root: Path, relative: str | os.PathLike[str]) -> Path:
    """Resolve ``relative`` inside ``root``; refuse absolute paths, ``..`` escapes and symlink escapes."""
    rel = str(relative).replace("\\", "/")
    if not rel or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise PathTraversalError(f"absolute or empty path refused: {relative!r}")
    if "\x00" in rel:
        raise PathTraversalError("NUL byte in path")
    if any(part == ".." for part in rel.split("/")):
        raise PathTraversalError(f"parent traversal refused: {relative!r}")
    root_resolved = root.resolve()
    candidate = (root_resolved / rel).resolve()
    if not is_within(root_resolved, candidate):
        raise PathTraversalError(f"path escapes repository root: {relative!r}")
    return candidate


def is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def to_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
