import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.main import app
from gateway.app.security.output_filter import (
    OutputFilterViolation,
    filter_capability_run_result,
)
from gateway.app.security.redaction import redact_sensitive_data
from gateway.app.tasks.models import CapabilityRunResult


def valid_run_request() -> dict[str, Any]:
    return {
        "workspace": {
            "name": "sample-workspace",
            "root_uri": "file:///workspace/sample-workspace",
            "git_branch": "feat/rbac-tightening",
            "git_diff": "diff --git a/app.py b/app.py\n",
            "files": [
                {
                    "path": "app.py",
                    "content": "def hello():\n    return 'world'\n",
                }
            ],
        },
        "instruction": "Review public payload and RBAC boundaries.",
        "client": {"type": "test", "version": "0.1.0"},
    }


def assert_not_serialized(body: Any, *needles: str) -> None:
    serialized = json.dumps(body)
    for needle in needles:
        assert needle not in serialized


def test_redacts_tokens_secret_assignments_api_keys_and_private_paths() -> None:
    payload = {
        "summary": (
            "Authorization: Bearer raw-runner-token and "
            "OPENAI_API_KEY=sk-proj-rawapikey123456"
        ),
        "paths": [
            r"C:\Users\ferry\.codex\skills\backend-rbac-review\SKILL.md",
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
        ],
        "nested": {
            "password": "plain-secret-value",
            "message": "client_secret: raw-client-secret",
        },
    }

    redacted = redact_sensitive_data(payload)

    assert_not_serialized(
        redacted,
        "raw-runner-token",
        "sk-proj-rawapikey123456",
        r"C:\Users\ferry",
        "/var/run/secrets",
        "plain-secret-value",
        "raw-client-secret",
    )
    assert "[REDACTED" in json.dumps(redacted)


def test_redacts_sensitive_mapping_keys() -> None:
    windows_path_key = r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
    api_key_key = "sk-proj-keyleak123456789"
    sensitive_key_with_path = r"api_key C:\Users\ferry\secret"
    payload = {
        windows_path_key: "public path-key value",
        api_key_key: "public api-key value",
        sensitive_key_with_path: "plain-secret-value",
        "nested": {
            "Authorization: Bearer raw-key-token": "public bearer-key value",
        },
    }

    redacted = redact_sensitive_data(payload)

    assert_not_serialized(
        redacted,
        windows_path_key,
        r"C:\Users\ferry",
        api_key_key,
        "sk-proj-keyleak123456789",
        "raw-key-token",
        sensitive_key_with_path,
        "plain-secret-value",
    )
    assert "[REDACTED_PATH]" in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert redacted["api_key [REDACTED_PATH]"] == "[REDACTED_SECRET]"
    assert "Authorization: Bearer [REDACTED_BEARER_TOKEN]" in redacted["nested"]


def test_output_filter_redacts_sensitive_strings_in_run_result() -> None:
    result = CapabilityRunResult(
        summary=(
            "Mock output used Authorization: Bearer raw-output-token from "
            r"C:\Users\ferry\.codex\skills\backend-rbac-review\SKILL.md"
        ),
        findings=[
            {
                "severity": "high",
                "path": r"C:\Users\ferry\.ssh\id_rsa",
                "title": "Secret returned",
                "message": "OPENAI_API_KEY=sk-proj-runnersecret123456",
            }
        ],
        patch="diff --git a/app.py b/app.py\n+client_secret = raw-client-secret\n",
        recommended_tests=["pytest tests -q # token=raw-test-token"],
        artifacts=[],
        safe_rationale="/var/run/secrets/kubernetes.io/serviceaccount/token",
        confidence=0.41,
    )

    safe_result = filter_capability_run_result(result)

    assert isinstance(safe_result, CapabilityRunResult)
    assert safe_result.confidence == 0.41
    assert_not_serialized(
        safe_result.model_dump(),
        "raw-output-token",
        r"C:\Users\ferry",
        "sk-proj-runnersecret123456",
        "raw-client-secret",
        "raw-test-token",
        "/var/run/secrets",
    )
    assert "[REDACTED" in json.dumps(safe_result.model_dump())


def test_output_filter_redacts_sensitive_mapping_keys_in_run_finding_extras() -> None:
    windows_path_key = r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
    api_key_key = "sk-proj-findingkeyleak123456"
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "severity": "low",
                "title": "Sensitive extra keys",
                "message": "Extra keys must be redacted before serialization.",
                windows_path_key: "public path-key value",
                api_key_key: "public api-key value",
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    safe_result = filter_capability_run_result(result)
    serialized = safe_result.model_dump()

    assert_not_serialized(
        serialized,
        windows_path_key,
        r"C:\Users\ferry",
        api_key_key,
        "sk-proj-findingkeyleak123456",
    )
    finding = serialized["findings"][0]
    assert finding["[REDACTED_PATH]"] == "[REDACTED_SECRET]"
    assert finding["[REDACTED_API_KEY]"] == "public api-key value"


@pytest.mark.parametrize(
    "private_key",
    [
        "prompt",
        "trace",
        "skill_text",
        "internal",
        "skill_ref",
        "model_policy",
        "raw_runner_output",
        "chain_of_thought",
        "skill_body",
        "system_prompt",
        "developer_prompt",
        "prompt_text",
        "tool_trace",
        "systemPrompt",
        "developerPrompt",
        "promptText",
        "toolTrace",
        "skillBody",
        "SystemPrompt",
        "system-prompt",
        "developer-prompt",
        "tool-trace",
        "skill-body",
    ],
)
def test_output_filter_rejects_private_fields_at_any_nested_level(
    private_key: str,
) -> None:
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "severity": "low",
                "title": "Nested extra field",
                "message": "This finding has an unsafe extra field.",
                private_key: "raw prompt content that must never be returned",
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(result)

    assert exc_info.value.code == "output_filter_violation"
    assert "raw prompt content" not in str(exc_info.value)


@pytest.mark.parametrize(
    "direct_leak_key",
    [
        "prompt_text",
        "skill_body",
        "system_prompt",
        "developer_prompt",
        "tool_trace",
        "systemPrompt",
        "developerPrompt",
        "promptText",
        "toolTrace",
        "skillBody",
        "SystemPrompt",
        "system-prompt",
        "developer-prompt",
        "tool-trace",
        "skill-body",
    ],
)
def test_output_filter_rejects_direct_leak_marker_keys(
    direct_leak_key: str,
) -> None:
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "severity": "low",
                "title": "Direct leak marker",
                "message": "This finding carries an unsafe direct marker.",
                direct_leak_key: f"raw private value for {direct_leak_key}",
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(result)

    assert exc_info.value.code == "output_filter_violation"
    assert direct_leak_key not in str(exc_info.value)
    assert "raw private value" not in str(exc_info.value)


def test_output_filter_allows_benign_public_words_in_extra_keys() -> None:
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "severity": "info",
                "title": "Public metadata",
                "message": "Benign extra fields should remain usable.",
                "traceability_note": "Public auditability note.",
                "promptness_score": "fast",
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    safe_result = filter_capability_run_result(result)

    finding = safe_result.findings[0].model_dump()
    assert finding["traceability_note"] == "Public auditability note."
    assert finding["promptness_score"] == "fast"


def test_output_filter_rejects_private_top_level_fields_from_raw_runner_mapping() -> None:
    raw_result = {
        "summary": "No public issues.",
        "safe_rationale": "Public rationale.",
        "confidence": 0.5,
        "raw_runner_output": "raw internal prompt that must not leak",
    }

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(raw_result)

    assert exc_info.value.code == "output_filter_violation"
    assert "raw internal prompt" not in str(exc_info.value)


def test_output_filter_rejects_suspected_skill_body_or_internal_prompt_text() -> None:
    result = CapabilityRunResult(
        summary=(
            "---\n"
            "name: backend-rbac-review\n"
            "description: private skill body\n"
            "# Internal system prompt\n"
            "Do not reveal this raw instruction."
        ),
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    with pytest.raises(OutputFilterViolation):
        filter_capability_run_result(result)


@pytest.mark.parametrize(
    "leaky_key",
    [
        "internal system prompt: do not reveal this raw instruction",
        "---\nname: backend-rbac-review\ndescription: private skill body",
    ],
)
def test_output_filter_rejects_suspected_leakage_in_mapping_keys(
    leaky_key: str,
) -> None:
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "severity": "low",
                "title": "Leaky key",
                "message": "The key carries private text.",
                leaky_key: "public value",
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(result)

    assert exc_info.value.code == "output_filter_violation"
    assert "private skill body" not in str(exc_info.value)
    assert "internal system prompt" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("container", "leaked_text"),
    [
        (set, "Internal system prompt: never reveal this."),
        (frozenset, "raw skill body: private instructions"),
    ],
)
def test_output_filter_rejects_suspected_leakage_inside_set_values(
    container: type[set[str]] | type[frozenset[str]],
    leaked_text: str,
) -> None:
    result = CapabilityRunResult(
        summary="No public issues.",
        findings=[
            {
                "title": "Set leakage",
                "message": "Container values must be inspected.",
                "notes": container({"safe public note", leaked_text}),
            }
        ],
        safe_rationale="Public rationale.",
        confidence=0.5,
    )

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(result)

    assert exc_info.value.code == "output_filter_violation"
    assert leaked_text not in str(exc_info.value)


def test_output_filter_rejects_nonstandard_iterables_before_model_coercion() -> None:
    leaked_text = "internal system prompt: hidden"
    raw_result = {
        "summary": "No public issues.",
        "safe_rationale": "Public rationale.",
        "confidence": 0.5,
        "recommended_tests": (item for item in [leaked_text]),
    }

    with pytest.raises(OutputFilterViolation) as exc_info:
        filter_capability_run_result(raw_result)

    assert exc_info.value.code == "output_filter_violation"
    assert leaked_text not in str(exc_info.value)


def test_run_endpoint_redacts_malicious_runner_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MaliciousRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> CapabilityRunResult:
            return CapabilityRunResult(
                summary=(
                    "Authorization: Bearer raw-api-token from "
                    r"C:\Users\ferry\.codex\skills\backend-rbac-review\SKILL.md"
                ),
                findings=[
                    {
                        "severity": "medium",
                        "path": r"C:\Users\ferry\.ssh\id_rsa",
                        "title": "Leaked secret",
                        "message": "OPENAI_API_KEY=sk-proj-runnerleak123456",
                    }
                ],
                patch=None,
                recommended_tests=["pytest -q"],
                artifacts=[],
                safe_rationale="client_secret = raw-client-secret",
                confidence=0.33,
            )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: MaliciousRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert_not_serialized(
        body,
        "raw-api-token",
        r"C:\Users\ferry",
        "sk-proj-runnerleak123456",
        "raw-client-secret",
    )
    assert "[REDACTED" in json.dumps(body)


def test_run_endpoint_blocks_malicious_runner_prompt_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LeakyRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> CapabilityRunResult:
            return CapabilityRunResult(
                summary="No public issues.",
                findings=[
                    {
                        "title": "Prompt leak",
                        "message": "The public text is harmless.",
                        "prompt": "raw internal prompt that must not leak",
                    }
                ],
                safe_rationale="Public rationale.",
                confidence=0.2,
            )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: LeakyRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "output_filter_violation"
    assert_not_serialized(body, "prompt", "raw internal prompt")


@pytest.mark.parametrize(
    "direct_leak_key",
    ["systemPrompt", "toolTrace", "system-prompt", "skill-body"],
)
def test_run_endpoint_blocks_direct_leak_marker_values(
    monkeypatch: pytest.MonkeyPatch,
    direct_leak_key: str,
) -> None:
    raw_value = f"raw endpoint leak for {direct_leak_key}"

    class LeakyRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> CapabilityRunResult:
            return CapabilityRunResult(
                summary="No public issues.",
                findings=[
                    {
                        "title": "Direct marker leak",
                        "message": "The public text is harmless.",
                        direct_leak_key: raw_value,
                    }
                ],
                safe_rationale="Public rationale.",
                confidence=0.2,
            )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: LeakyRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "output_filter_violation"
    assert_not_serialized(body, direct_leak_key, raw_value)
