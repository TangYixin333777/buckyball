#!/usr/bin/env python3
"""PreToolUse hook: block dangerous terminal operations and protected-path edits."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict


DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bDROP\s+TABLE\b",
]

PROTECTED_PREFIXES = [
    ".github/hooks/",
    "scripts/hooks/",
]

EDIT_TOOL_HINTS = {
    "create_file",
    "replace_string_in_file",
    "insert_edit_into_file",
    "delete_file",
    "apply_patch",
    "editFiles",
    "writeFile",
    "replace_string",
}


def get_value(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def deny(reason: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def allow_with_context(message: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }
    if message:
        payload["hookSpecificOutput"]["additionalContext"] = message
    return payload


def _is_dangerous_terminal(tool_name: str, tool_input: Dict[str, Any]) -> str | None:
    if tool_name not in {"run_in_terminal", "terminal", "runTerminalCommand"}:
        return None
    command = str(get_value(tool_input, "command", "cmd", "text") or "")
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return f"Dangerous terminal command blocked: {command}"
    return None


def _iter_candidate_paths(tool_input: Dict[str, Any]) -> list[str]:
    candidates = []
    for key in ("filePath", "path", "target", "includePattern"):
        value = get_value(tool_input, key)
        if isinstance(value, str):
            candidates.append(value)

    files_value = get_value(tool_input, "files")
    if isinstance(files_value, list):
        for item in files_value:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                path = get_value(item, "filePath", "path")
                if isinstance(path, str):
                    candidates.append(path)

    return candidates


def _targets_protected_paths(tool_name: str, tool_input: Dict[str, Any]) -> str | None:
    if tool_name not in EDIT_TOOL_HINTS:
        return None

    for raw_path in _iter_candidate_paths(tool_input):
        normalized = raw_path.replace("\\", "/").lstrip("./")
        for prefix in PROTECTED_PREFIXES:
            if normalized.startswith(prefix):
                return f"Protected path edit denied: {raw_path}"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(
            json.dumps(allow_with_context("Hook input parse failed; allow by default."))
        )
        return 0

    tool_name = str(get_value(payload, "tool_name", "toolName") or "")
    tool_input = get_value(payload, "tool_input", "toolInput")
    if not isinstance(tool_input, dict):
        tool_input = {}

    reason = _is_dangerous_terminal(tool_name, tool_input)
    if reason:
        print(json.dumps(deny(reason), ensure_ascii=True))
        return 0

    reason = _targets_protected_paths(tool_name, tool_input)
    if reason:
        print(json.dumps(deny(reason), ensure_ascii=True))
        return 0

    print(json.dumps(allow_with_context(), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
