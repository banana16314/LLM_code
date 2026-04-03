"""Permission management — mirrors Claude Code's multi-layer permission system.

Key design (from source):
1. User says "Yes, don't ask again" → rule persisted to settings.json → never ask again
2. acceptEdits mode → file operations in CWD auto-allowed
3. Dangerous commands → always ask, even in bypass mode
4. Rules stored in ~/.claude/settings.json, survive across sessions
"""

from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum

log = logging.getLogger(__name__)

SETTINGS_FILE = os.path.expanduser("~/.claude/settings.json")


class Permission(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# Default rules: tool_name -> permission
DEFAULT_RULES: dict[str, Permission] = {
    # Read-only tools — always allow
    "Read": Permission.ALLOW,
    "Glob": Permission.ALLOW,
    "Grep": Permission.ALLOW,
    "TaskList": Permission.ALLOW,
    "TaskGet": Permission.ALLOW,
    "TaskCreate": Permission.ALLOW,
    "TaskUpdate": Permission.ALLOW,
    "AskUserQuestion": Permission.ALLOW,
    "CronCreate": Permission.ALLOW,
    "CronDelete": Permission.ALLOW,
    "CronList": Permission.ALLOW,
    "EnterPlanMode": Permission.ALLOW,
    "ExitPlanMode": Permission.ALLOW,
    # Write tools — ask first time, then remember
    "Bash": Permission.ASK,
    "Edit": Permission.ASK,
    "Write": Permission.ASK,
    "NotebookEdit": Permission.ASK,
    # Agent / web — allow
    "Agent": Permission.ALLOW,
    "WebSearch": Permission.ALLOW,
    "WebFetch": Permission.ALLOW,
}

# Dangerous bash patterns — always ask, cannot be bypassed
DANGEROUS_PATTERNS_RE = [
    r"rm\s+-rf\s+[/~]", r"rm\s+-rf\s+\.", r"git\s+push\s+--force",
    r"git\s+reset\s+--hard", r"git\s+clean\s+-f", r"git\s+checkout\s+--\s+\.",
    r"git\s+branch\s+-D", r"drop\s+table", r"drop\s+database",
    r">\s*/dev/sd", r"mkfs\.", r"dd\s+if=", r":()\{\s*:\|:&\s*\};:",
    r"chmod\s+-R\s+777", r"curl.*\|\s*(bash|sh)",
]


def _is_dangerous_bash(cmd: str) -> bool:
    for pat in DANGEROUS_PATTERNS_RE:
        if re.search(pat, cmd):
            return True
    return False


class PermissionManager:
    """Multi-layer permission system mirroring Claude Code source.

    Decision order:
    1. Dangerous Bash → always ASK (even in bypass)
    2. auto_approve mode → ALLOW everything else
    3. Persisted "always allow" rules (from settings.json) → ALLOW
    4. Session grants (from "a" answer in current session) → ALLOW
    5. Default rules → whatever the tool's default is
    """

    def __init__(self, auto_approve: bool = False, cwd: str = ""):
        self._rules: dict[str, Permission] = dict(DEFAULT_RULES)
        self._session_tool_allows: set[str] = set()
        self._bash_prefix_allows: set[str] = set()
        self.auto_approve = auto_approve
        self.cwd = cwd
        # Load persisted rules from disk
        self._persisted_allows: set[str] = set()
        self._load_persisted_rules()

    # ── Core check ──────────────────────────────────────────────────

    def check(self, tool_name: str, args: dict) -> Permission:
        # 1. Dangerous Bash — always ask, no bypass
        if tool_name == "Bash":
            cmd = args.get("command", "")
            if _is_dangerous_bash(cmd):
                return Permission.ASK

        # 2. Bypass mode (--yes flag)
        if self.auto_approve:
            return Permission.ALLOW

        # 3. Persisted "always allow" rules (from settings.json)
        if tool_name in self._persisted_allows:
            # For Bash, also check persisted prefix rules
            if tool_name == "Bash":
                cmd = args.get("command", "").strip()
                prefix = cmd.split()[0] if cmd else ""
                if f"Bash:{prefix}" in self._persisted_allows or "Bash" in self._persisted_allows:
                    return Permission.ALLOW
            else:
                return Permission.ALLOW

        # 4. Session grants (from "a" answer this session)
        if tool_name in self._session_tool_allows:
            return Permission.ALLOW
        if tool_name == "Bash":
            cmd = args.get("command", "").strip()
            prefix = cmd.split()[0] if cmd else ""
            if prefix and prefix in self._bash_prefix_allows:
                return Permission.ALLOW

        # 5. Default rules
        return self._rules.get(tool_name, Permission.ASK)

    # ── Grant methods ───────────────────────────────────────────────

    def grant_session_tool(self, tool_name: str):
        """Allow a tool for this session (in-memory only)."""
        self._session_tool_allows.add(tool_name)

    def grant_bash_prefix(self, command: str):
        """Allow a Bash command prefix for this session."""
        prefix = command.strip().split()[0] if command.strip() else ""
        if prefix:
            self._bash_prefix_allows.add(prefix)

    def grant_persistent(self, tool_name: str):
        """Persist an always-allow rule to settings.json (survives restart)."""
        self._persisted_allows.add(tool_name)
        self._save_persisted_rules()

    def set_rule(self, tool_name: str, perm: Permission):
        self._rules[tool_name] = perm

    # ── Persistence (settings.json) ─────────────────────────────────

    def _load_persisted_rules(self):
        """Load persisted permission rules from ~/.claude/settings.json."""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                rules = data.get("permissions", {}).get("allow", [])
                for rule in rules:
                    if isinstance(rule, str):
                        self._persisted_allows.add(rule)
                    elif isinstance(rule, dict):
                        self._persisted_allows.add(rule.get("tool", ""))
        except Exception as e:
            log.debug(f"Could not load permission rules: {e}")

    def _save_persisted_rules(self):
        """Save permission rules to ~/.claude/settings.json."""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            data = {}
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)

            if "permissions" not in data:
                data["permissions"] = {}
            data["permissions"]["allow"] = sorted(self._persisted_allows)

            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            log.debug(f"Could not save permission rules: {e}")
