import json
import subprocess
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.auth.models import RequestIdentity
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry
from gateway.app.main import app
from gateway.app.runners.hermes_runner import HermesCapabilityRunner, HermesRunnerError
from gateway.app.runners.json_output import parse_runner_json_output
from gateway.app.security.input_policy import WorkspaceInputFile
from gateway.app.tasks.models import CapabilityRunResult


PRIVATE_SKILL_TEXT = "internal system prompt: do not reveal this skill body"
RAW_PRIVATE_OUTPUT = "raw internal prompt that must not leak"
RAW_RUNNER_STDOUT = "raw stdout with prompt and skill text"
RAW_RUNNER_STDERR = "raw stderr with developer prompt and trace"


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
        "options": {"return_patch": True},
        "client": {"type": "test", "version": "0.1.0"},
    }


def valid_runner_output(**updates: Any) -> str:
    payload: dict[str, Any] = {
        "summary": "Hermes review completed.",
        "findings": [],
        "patch": None,
        "recommended_tests": ["python -m pytest"],
        "artifacts": [],
        "safe_rationale": "Public rationale only.",
        "confidence": 0.88,
    }
    payload.update(updates)
    return json.dumps(payload)


def backend_rbac_capability(*, runner: str = "hermes") -> CapabilityManifest:
    capability = default_registry().find("backend-rbac-review")
    assert capability is not None
    return capability.model_copy(
        update={
            "internal": capability.internal.model_copy(
                update={
                    "runner": runner,
                    "skill_body": PRIVATE_SKILL_TEXT,
                }
            )
        }
    )


class StubRegistry:
    def __init__(self, capability: CapabilityManifest) -> None:
        self._capability = capability

    def find(self, capability_id: str) -> CapabilityManifest | None:
        if capability_id == self._capability.id:
            return self._capability
        return None


def use_capability(monkeypatch: pytest.MonkeyPatch, capability: CapabilityManifest) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "default_registry",
        lambda: StubRegistry(capability),
    )


def assert_sanitized_exception(exc: BaseException, *raw_values: str) -> None:
    serialized = str(exc)
    for raw_value in raw_values:
        assert raw_value not in serialized
    assert "prompt" not in serialized.lower()
    assert "skill text" not in serialized.lower()
    assert "skill body" not in serialized.lower()
    assert "trace" not in serialized.lower()


def assert_no_exception_chain(exc: BaseException) -> None:
    assert exc.__cause__ is None
    assert exc.__context__ is None


def assert_sanitized_exception_chain(exc: BaseException, *raw_values: str) -> None:
    assert_no_exception_chain(exc)
    assert_sanitized_exception(exc, *raw_values)


def assert_not_serialized(body: Any, *raw_values: str) -> None:
    serialized = json.dumps(body)
    for raw_value in raw_values:
        assert raw_value not in serialized


def test_parse_runner_json_output_accepts_valid_object_and_filters_result() -> None:
    output = valid_runner_output(
        summary="Authorization: Bearer raw-hermes-token",
        safe_rationale="OPENAI_API_KEY=sk-proj-hermesrunner123456",
    )

    result = parse_runner_json_output(output)

    assert isinstance(result, CapabilityRunResult)
    assert result.confidence == 0.88
    serialized = result.model_dump()
    assert_not_serialized(
        serialized,
        "raw-hermes-token",
        "sk-proj-hermesrunner123456",
    )
    assert "[REDACTED" in json.dumps(serialized)


@pytest.mark.parametrize(
    "output",
    [
        "{not json",
        valid_runner_output() + "\nHermes explanation outside JSON",
        "```json\n" + valid_runner_output() + "\n```",
        json.dumps([{"summary": "arrays are not valid runner output"}]),
        json.dumps("strings are not valid runner output"),
        json.dumps({"summary": "missing required fields"}),
    ],
)
def test_parse_runner_json_output_rejects_invalid_output_safely(output: str) -> None:
    with pytest.raises(HermesRunnerError) as exc_info:
        parse_runner_json_output(output)

    assert str(exc_info.value) == "Hermes runner returned invalid JSON output."
    assert_sanitized_exception_chain(exc_info.value, output)


def test_parse_runner_json_output_rejects_schema_invalid_output_without_chain() -> None:
    output = valid_runner_output(prompt=RAW_PRIVATE_OUTPUT)

    with pytest.raises(HermesRunnerError) as exc_info:
        parse_runner_json_output(output)

    assert str(exc_info.value) == "Hermes runner returned invalid JSON output."
    assert_sanitized_exception_chain(exc_info.value, output, RAW_PRIVATE_OUTPUT)


def test_parse_runner_json_output_rejects_private_fields_safely() -> None:
    output = valid_runner_output(
        findings=[
            {
                "title": "Prompt leak",
                "message": "Harmless public text.",
                "prompt": RAW_PRIVATE_OUTPUT,
            }
        ]
    )

    with pytest.raises(HermesRunnerError) as exc_info:
        parse_runner_json_output(output)

    assert str(exc_info.value) == "Hermes runner returned unsafe output."
    assert_sanitized_exception_chain(exc_info.value, output, RAW_PRIVATE_OUTPUT)


def test_parse_runner_json_output_rejects_duplicate_keys_before_smuggling() -> None:
    output = (
        "{"
        '"summary":"Hermes review completed.",'
        f'"findings":[{{"prompt":{json.dumps(RAW_PRIVATE_OUTPUT)}}}],'
        '"findings":[],'
        '"patch":null,'
        '"recommended_tests":["python -m pytest"],'
        '"artifacts":[],'
        '"safe_rationale":"Public rationale only.",'
        '"confidence":0.88'
        "}"
    )

    with pytest.raises(HermesRunnerError) as exc_info:
        parse_runner_json_output(output)

    assert str(exc_info.value) == "Hermes runner returned invalid JSON output."
    assert_sanitized_exception_chain(exc_info.value, output, RAW_PRIVATE_OUTPUT)


def test_hermes_runner_calls_subprocess_with_skill_ref_but_not_skill_body() -> None:
    calls: list[tuple[Sequence[str], dict[str, Any]]] = []

    def run_process(
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=valid_runner_output(),
            stderr="",
        )

    capability = backend_rbac_capability()
    runner = HermesCapabilityRunner(run_process=run_process)
    request = capabilities_api.CapabilityRunRequest.model_validate(valid_run_request())

    result = runner.run(
        capability,
        request,
        [WorkspaceInputFile(path="app.py", content="def hello():\n    return 'world'\n")],
    )

    assert result.summary == "Hermes review completed."
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert tuple(command) == (
        "hermes",
        "run",
        "--skill",
        "backend-rbac-review",
        "--json",
    )
    payload = json.loads(kwargs["input"])
    serialized_payload = json.dumps(payload)
    assert payload["capability"] == {
        "id": "backend-rbac-review",
        "name": "Backend RBAC Review",
        "skill_ref": "backend-rbac-review",
    }
    assert "request" in payload
    assert "workspace_files" in payload
    assert "internal" not in serialized_payload
    assert "model_policy" not in serialized_payload
    assert PRIVATE_SKILL_TEXT not in serialized_payload
    assert kwargs["text"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False


def test_hermes_runner_rejects_nonzero_subprocess_result_safely() -> None:
    def run_process(
        command: Sequence[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=2,
            stdout=RAW_RUNNER_STDOUT,
            stderr=RAW_RUNNER_STDERR,
        )

    runner = HermesCapabilityRunner(run_process=run_process)
    request = capabilities_api.CapabilityRunRequest.model_validate(valid_run_request())

    with pytest.raises(HermesRunnerError) as exc_info:
        runner.run(backend_rbac_capability(), request, [])

    assert str(exc_info.value) == "Hermes runner process failed."
    assert_sanitized_exception_chain(
        exc_info.value,
        RAW_RUNNER_STDOUT,
        RAW_RUNNER_STDERR,
    )


@pytest.mark.parametrize(
    "raised",
    [
        subprocess.TimeoutExpired(
            cmd=("hermes", "run"),
            timeout=30,
            output=RAW_RUNNER_STDOUT,
            stderr=RAW_RUNNER_STDERR,
        ),
        OSError("could not start hermes with raw prompt"),
    ],
)
def test_hermes_runner_rejects_process_exceptions_safely(raised: Exception) -> None:
    def run_process(
        _command: Sequence[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        raise raised

    runner = HermesCapabilityRunner(run_process=run_process)
    request = capabilities_api.CapabilityRunRequest.model_validate(valid_run_request())

    with pytest.raises(HermesRunnerError) as exc_info:
        runner.run(backend_rbac_capability(), request, [])

    assert_sanitized_exception_chain(
        exc_info.value,
        RAW_RUNNER_STDOUT,
        RAW_RUNNER_STDERR,
        "could not start hermes with raw prompt",
    )


def test_run_endpoint_uses_hermes_runner_and_returns_filtered_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_process(
        command: Sequence[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=valid_runner_output(
                summary="Authorization: Bearer api-path-token",
                safe_rationale="client_secret = api-path-secret",
            ),
            stderr="",
        )

    use_capability(monkeypatch, backend_rbac_capability())
    monkeypatch.setattr("gateway.app.runners.hermes_runner.subprocess.run", run_process)
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["confidence"] == 0.88
    assert_not_serialized(body, "api-path-token", "api-path-secret")
    assert "[REDACTED" in json.dumps(body)


def test_run_endpoint_returns_redacted_error_when_hermes_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_process(
        command: Sequence[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout=RAW_RUNNER_STDOUT,
            stderr=RAW_RUNNER_STDERR,
        )

    use_capability(monkeypatch, backend_rbac_capability())
    monkeypatch.setattr("gateway.app.runners.hermes_runner.subprocess.run", run_process)
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "hermes_runner_error"
    assert body["error"]["message"] == "Hermes runner process failed."
    assert_not_serialized(body, RAW_RUNNER_STDOUT, RAW_RUNNER_STDERR)


def test_run_capability_converts_hermes_error_without_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_process(
        command: Sequence[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout=RAW_RUNNER_STDOUT,
            stderr=RAW_RUNNER_STDERR,
        )

    use_capability(monkeypatch, backend_rbac_capability())
    monkeypatch.setattr("gateway.app.runners.hermes_runner.subprocess.run", run_process)
    request = capabilities_api.CapabilityRunRequest.model_validate(valid_run_request())
    identity = RequestIdentity(auth_mode="dev", tenant_id="default", role="developer")

    with pytest.raises(HTTPException) as exc_info:
        capabilities_api.run_capability("backend-rbac-review", request, identity)

    assert_no_exception_chain(exc_info.value)
    assert_sanitized_exception(exc_info.value, RAW_RUNNER_STDOUT, RAW_RUNNER_STDERR)
