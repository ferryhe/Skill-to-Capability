#!/usr/bin/env python3
"""Request the sample RBAC patch from a local Skill Gateway."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "sample-workspace"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"
DEFAULT_CAPABILITY_ID = "backend-rbac-review"
TEST_COMMAND = "python -m unittest discover -s tests -v"
FORBIDDEN_RESPONSE_KEYS = {
    "internal",
    "model_policy",
    "skill_ref",
    "skill_body",
    "skill_text",
    "system_prompt",
    "developer_prompt",
    "prompt",
    "trace",
    "raw_runner_output",
}
SECRET_LIKE_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\b[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\b\s*[:=]",
        re.I,
    ),
    re.compile(r'"(?:password|secret|token|api_key)"\s*:', re.I),
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{8,}"),
)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    sample_root = Path(args.sample).resolve()
    app_path = sample_root / "app.py"
    if not app_path.is_file():
        print("sample app.py was not found.", file=sys.stderr)
        return 2

    app_content = app_path.read_text(encoding="utf-8")
    payload = _run_payload(sample_root, app_content)
    gateway_url = args.gateway_url.rstrip("/")
    url = f"{gateway_url}/v1/capabilities/{args.capability}/run"

    try:
        response_body = _post_json(url, payload, token=args.token)
    except GatewayRequestError as exc:
        print(exc.safe_message, file=sys.stderr)
        return 2

    if _contains_forbidden_response_key(response_body):
        print("Gateway response included server-only fields.", file=sys.stderr)
        return 2
    if _contains_secret_like_value(response_body):
        print("Gateway response included secret-like values.", file=sys.stderr)
        return 2

    result = response_body.get("result") if isinstance(response_body, dict) else None
    patch = result.get("patch") if isinstance(result, dict) else None
    if not isinstance(patch, str) or not patch.strip():
        print("Gateway response did not include a patch.", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "run-result.json"
    patch_path = out_dir / "fix-rbac.patch"
    result_path.write_text(json.dumps(response_body, indent=2) + "\n", encoding="utf-8")
    patch_path.write_text(patch, encoding="utf-8")

    print(
        json.dumps(
            {
                "task_id": response_body.get("task_id"),
                "status": response_body.get("status"),
                "result_path": str(result_path),
                "patch_path": str(patch_path),
                "recommended_tests": result.get("recommended_tests", [TEST_COMMAND]),
            },
            indent=2,
        )
    )
    return 0


class GatewayRequestError(RuntimeError):
    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Request the H2 sample RBAC patch from a local Gateway.",
    )
    parser.add_argument("--gateway-url", default=os.getenv("GATEWAY_URL", DEFAULT_GATEWAY_URL))
    parser.add_argument("--capability", default=DEFAULT_CAPABILITY_ID)
    parser.add_argument("--sample", default=str(SAMPLE_ROOT))
    parser.add_argument("--out-dir", default=str(SAMPLE_ROOT / ".skillgw"))
    parser.add_argument("--token", default=os.getenv("GATEWAY_TOKEN"))
    return parser


def _run_payload(sample_root: Path, app_content: str) -> dict[str, Any]:
    return {
        "workspace": {
            "name": sample_root.name,
            "root_uri": sample_root.as_uri(),
            "git_branch": "h2-e2e-sample",
            "files": [
                {
                    "path": "app.py",
                    "content": app_content,
                    "sha256": hashlib.sha256(app_content.encode("utf-8")).hexdigest(),
                }
            ],
        },
        "instruction": (
            "Review the sample RBAC guard and return a safe unified diff patch "
            "if the admin report access check is too broad."
        ),
        "options": {"return_patch": True},
        "client": {"type": "cli", "version": "h2-sample"},
    }


def _post_json(url: str, payload: dict[str, Any], *, token: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GatewayRequestError(
            f"Gateway returned HTTP {exc.code}: {_safe_error_excerpt(body, token)}"
        ) from None
    except urllib.error.URLError:
        raise GatewayRequestError("Could not reach the Gateway.") from None

    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError:
        raise GatewayRequestError("Gateway returned non-JSON output.") from None
    if not isinstance(decoded, dict):
        raise GatewayRequestError("Gateway returned an unexpected JSON shape.")
    return decoded


def _safe_error_excerpt(body: str, token: str | None) -> str:
    safe_body = body
    if token:
        safe_body = safe_body.replace(token, "[redacted-token]")
    try:
        decoded = json.loads(safe_body)
    except json.JSONDecodeError:
        excerpt = safe_body[:1000]
        if _string_contains_secret_like_value(excerpt):
            return "Gateway error body suppressed for safety."
        if _string_contains_forbidden_response_key(excerpt):
            return "Gateway error body suppressed for safety."
        return excerpt
    if _contains_forbidden_response_key(decoded) or _contains_secret_like_value(decoded):
        return "Gateway error body suppressed for safety."
    return safe_body[:1000]


def _contains_forbidden_response_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in FORBIDDEN_RESPONSE_KEYS:
                return True
            if _contains_forbidden_response_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_response_key(item) for item in value)
    return False


def _contains_secret_like_value(value: Any) -> bool:
    if isinstance(value, str):
        return _string_contains_secret_like_value(value)
    if isinstance(value, dict):
        return any(_contains_secret_like_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_secret_like_value(item) for item in value)
    return False


def _string_contains_secret_like_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_LIKE_VALUE_PATTERNS)


def _string_contains_forbidden_response_key(value: str) -> bool:
    normalized_value = value.casefold()
    return any(key in normalized_value for key in FORBIDDEN_RESPONSE_KEYS)


if __name__ == "__main__":
    raise SystemExit(main())
