#!/usr/bin/env python3
"""Safe fake Hermes runner for the H2 end-to-end sample."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "sample-workspace"
PATCH_PATH = SAMPLE_ROOT / "patches" / "fix-rbac.patch"
BUG_SNIPPET = (
    "def can_view_admin_report(user: User) -> bool:\n"
    "    # BUG: this grants every active user access to the admin report.\n"
    "    return user.is_active"
)
TEST_COMMAND = "python -m unittest discover -s tests -v"


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("fake runner received invalid JSON input.", file=sys.stderr)
        return 2

    workspace_files = payload.get("workspace_files")
    if not isinstance(workspace_files, list):
        print("fake runner input is missing workspace files.", file=sys.stderr)
        return 2

    app_content = _workspace_file_content(workspace_files, "app.py").replace("\r\n", "\n")
    patch = PATCH_PATH.read_text(encoding="utf-8") if BUG_SNIPPET in app_content else None
    result = {
        "summary": (
            "Sample RBAC review found a patchable admin report access bug."
            if patch is not None
            else "Sample RBAC review found no patchable bug."
        ),
        "findings": (
            [
                {
                    "severity": "high",
                    "path": "app.py",
                    "line": 13,
                    "title": "Active users bypass admin-only report access",
                    "message": (
                        "The guard checks only is_active, so any active user can "
                        "view the admin report."
                    ),
                }
            ]
            if patch is not None
            else []
        ),
        "patch": patch,
        "recommended_tests": [TEST_COMMAND],
        "artifacts": [],
        "safe_rationale": (
            "This fake runner reads only the public runner payload and returns "
            "a deterministic public run-result JSON object for the sample."
        ),
        "confidence": 0.94,
    }
    json.dump(result, sys.stdout, separators=(",", ":"))
    return 0


def _workspace_file_content(workspace_files: list[Any], relative_path: str) -> str:
    for workspace_file in workspace_files:
        if not isinstance(workspace_file, dict):
            continue
        if workspace_file.get("path") == relative_path:
            content = workspace_file.get("content")
            return content if isinstance(content, str) else ""
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
