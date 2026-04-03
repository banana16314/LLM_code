"""Git utilities."""

from __future__ import annotations

import os
import subprocess


def is_git_repo(path: str) -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path, capture_output=True, check=True, timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_git_branch(path: str) -> str:
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_git_status(path: str) -> str:
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=path, capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_git_root(path: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path, capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_git_info(path: str) -> str:
    if not is_git_repo(path):
        return ""
    branch = get_git_branch(path)
    root = get_git_root(path)
    parts = [
        f"- Working directory: {path}",
        f"- Git repository: {root}",
    ]
    if branch:
        parts.append(f"- Branch: {branch}")
    return "\n".join(parts)
