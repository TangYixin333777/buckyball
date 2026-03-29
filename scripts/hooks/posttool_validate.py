#!/usr/bin/env python3
"""PostToolUse hook: provide additional context when required rule files are missing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


REQUIRED_RULES = [
    ".buckyball-rules/00-orchestration.md",
    ".buckyball-rules/01-hw-interface.md",
    ".buckyball-rules/03-ball-registration.md",
    ".buckyball-rules/06-verify-checklist.md",
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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({}))
        return 0

    tool_name = str(get_value(payload, "tool_name", "toolName") or "")
    if tool_name not in EDIT_TOOL_HINTS:
        print(json.dumps({}))
        return 0

    cwd = Path(str(get_value(payload, "cwd") or ".")).resolve()
    missing = [rule for rule in REQUIRED_RULES if not (cwd / rule).exists()]
    if not missing:
        print(json.dumps({}))
        return 0

    additional_context = (
        "Required Buckyball rule files are missing: "
        + ", ".join(missing)
        + ". Generate or restore rules before continuing author/registrar stages."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": additional_context,
        },
        "systemMessage": additional_context,
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
