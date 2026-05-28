import json
import subprocess
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.runners.hermes_runner import HermesCapabilityRunner
from gateway.app.security.input_policy import WorkspaceInputFile

from helpers import (
    FULL_PROMPT_MARKER,
    RAW_FULL_PROMPT,
    RAW_RUNNER_OUTPUT,
    RAW_SKILL_BODY,
    RAW_SYSTEM_PROMPT,
    RUNNER_OUTPUT_MARKER,
    SKILL_BODY_MARKER,
    SYSTEM_PROMPT_MARKER,
    assert_error_response,
    assert_not_serialized,
    backend_rbac_capability,
    public_result,
    valid_run_request,
)


def test_capability_public_endpoints_strip_internal_manifest_fields(
    client: TestClient,
) -> None:
    list_response = client.get("/v1/capabilities")
    detail_response = client.get("/v1/capabilities/backend-rbac-review")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert_not_serialized(
        [list_response.json(), detail_response.json()],
        "internal",
        "skill_ref",
        "model_policy",
        "expose_skill_text",
        "required_env",
        "required_commands",
        RAW_SKILL_BODY,
    )


def test_hermes_runner_payload_uses_skill_ref_without_skill_body_or_prompt() -> None:
    captured_payloads: list[dict[str, Any]] = []

    def run_process(
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        captured_payloads.append(json.loads(kwargs["input"]))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(public_result()),
            stderr="",
        )

    capability = backend_rbac_capability(
        skill_body=RAW_SKILL_BODY,
        full_prompt=RAW_FULL_PROMPT,
    )
    request = capabilities_api.CapabilityRunRequest.model_validate(valid_run_request())
    runner = HermesCapabilityRunner(run_process=run_process)

    runner.run(
        capability,
        request,
        [WorkspaceInputFile(path="app.py", content="print('ok')\n")],
    )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["capability"] == {
        "id": "backend-rbac-review",
        "name": "Backend RBAC Review",
        "skill_ref": "backend-rbac-review",
    }
    assert_not_serialized(
        payload,
        "skill_body",
        "full_prompt",
        SKILL_BODY_MARKER,
        FULL_PROMPT_MARKER,
        RAW_SKILL_BODY,
        RAW_FULL_PROMPT,
    )


@pytest.mark.parametrize(
    ("leaky_summary", "marker"),
    [
        (RAW_SKILL_BODY, SKILL_BODY_MARKER),
        (RAW_SYSTEM_PROMPT, SYSTEM_PROMPT_MARKER),
        (RAW_FULL_PROMPT, FULL_PROMPT_MARKER),
        (RAW_RUNNER_OUTPUT, RUNNER_OUTPUT_MARKER),
    ],
)
def test_run_endpoint_blocks_internal_text_leaks_from_runner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    leaky_summary: str,
    marker: str,
) -> None:
    class LeakyRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return public_result(summary=leaky_summary)

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: LeakyRunner(),
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 502
    body = response.json()
    assert_error_response(body, "output_filter_violation")
    assert_not_serialized(body, marker, leaky_summary)


def test_run_endpoint_blocks_raw_runner_output_field(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LeakyRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return public_result(raw_runner_output=RAW_RUNNER_OUTPUT)

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: LeakyRunner(),
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 502
    body = response.json()
    assert_error_response(body, "output_filter_violation")
    assert_not_serialized(body, "raw_runner_output", RUNNER_OUTPUT_MARKER)
