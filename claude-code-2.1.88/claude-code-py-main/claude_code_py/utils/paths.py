"""Path utilities."""

from __future__ import annotations

import os


def expand_path(path: str, cwd: str = "") -> str:
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    return os.path.normpath(path)


def to_relative_path(path: str, cwd: str = "") -> str:
    cwd = cwd or os.getcwd()
    try:
        return os.path.relpath(path, cwd)
    except ValueError:
        return path
