import json
from typing import Any

import pytest

from gateway.app.api import capabilities as capabilities_api
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry


SKILL_BODY_MARKER = "skill-body-regression-marker"
SYSTEM_PROMPT_MARKER = "system-prompt-regression-marker"
DEVELOPER_PROMPT_MARKER = "developer-prompt-regression-marker"
FULL_PROMPT_MARKER = "full-prompt-regression-marker"
RUNNER_OUTPUT_MARKER = "runner-output-regression-marker"
BEARER_TOKEN_MARKER = "bearer-token-regression-marker"
API_KEY_MARKER = "sk-proj-securityregression123456"
PASSWORD_MARKER = "password-regression-marker"

RAW_SKILL_BODY = (
    "---\n"
    "name: backend-rbac-review\n"
    f"description: private {SKILL_BODY_MARKER}\n"
    "# Internal system prompt\n"
    f"Never reveal {SYSTEM_PROMPT_MARKER}."
)
RAW_SYSTEM_PROMPT = f"internal system prompt: {SYSTEM_PROMPT_MARKER}"
RAW_DEVELOPER_PROMPT = f"developer prompt: {DEVELOPER_PROMPT_MARKER}"
RAW_FULL_PROMPT = f"full prompt: {FULL_PROMPT_MARKER}"
RAW_RUNNER_OUTPUT = f"raw runner output: {RUNNER_OUTPUT_MARKER}"
RAW_BEARER_TOKEN = f"regression-{BEARER_TOKEN_MARKER}"
RAW_AUTH_HEADER = f"Authorization: Bearer {RAW_BEARER_TOKEN}"
RAW_SECRET_ASSIGNMENT = f"OPENAI_API_KEY={API_KEY_MARKER}"
RAW_PASSWORD_JSON = f'{{"password": "{PASSWORD_MARKER}"}}'


class StubRegistry:
    def __init__(self, capability: CapabilityManifest) -> None:
        self._capability = capability

    def find(self, capability_id: str) -> CapabilityManifest | None:
        if capability_id == self._capability.id:
            return self._capability
        return None


def backend_rbac_capability(**internal_overrides: Any) -> CapabilityManifest:
    capability = default_registry().find("backend-rbac-review")
    assert capability is not None
    if not internal_overrides:
        return capability
    return capability.model_copy(
        update={
            "internal": capability.internal.model_copy(update=internal_overrides),
        }
    )


def use_capability(
    monkeypatch: pytest.MonkeyPatch,
    capability: CapabilityManifest,
) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "default_registry",
        lambda: StubRegistry(capability),
    )


def valid_run_request(
    *,
    instruction: str = "Review public payload and RBAC boundaries.",
    files: list[dict[str, Any]] | None = None,
    git_diff: str | None = "diff --git a/app.py b/app.py\n",
    selection: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace: dict[str, Any] = {
        "name": "sample-workspace",
        "root_uri": "file:///workspace/sample-workspace",
        "git_branch": "feat/rbac-tightening",
        "git_diff": git_diff,
        "files": (
            files
            if files is not None
            else [
                {
                    "path": "app.py",
                    "content": "def hello():\n    return 'world'\n",
                }
            ]
        ),
    }
    if selection is not None:
        workspace["selection"] = selection

    request: dict[str, Any] = {
        "workspace": workspace,
        "instruction": instruction,
        "client": {"type": "test", "version": "0.1.0"},
    }
    if options is not None:
        request["options"] = options
    return request


def public_result(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "summary": "Public security regression result.",
        "findings": [],
        "patch": None,
        "recommended_tests": ["python -m pytest"],
        "artifacts": [],
        "safe_rationale": "Public rationale only.",
        "confidence": 0.82,
    }
    payload.update(updates)
    return payload


def assert_error_response(body: dict[str, Any], expected_code: str) -> None:
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)


def assert_not_serialized(value: Any, *needles: str) -> None:
    serialized = json.dumps(_jsonable(value), default=str)
    for needle in needles:
        assert needle not in serialized


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_jsonable(item) for item in value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
