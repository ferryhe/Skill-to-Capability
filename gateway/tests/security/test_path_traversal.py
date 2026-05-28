from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api

from helpers import (
    assert_error_response,
    assert_not_serialized,
    backend_rbac_capability,
    public_result,
    use_capability,
    valid_run_request,
)


@pytest.mark.parametrize(
    ("unsafe_path", "expected_code"),
    [
        ("../secret.py", "path_traversal"),
        ("src/../../secret.py", "path_traversal"),
        ("..\\secret.py", "path_traversal"),
        ("src\\..\\..\\secret.py", "path_traversal"),
        ("/etc/passwd", "absolute_path"),
        (r"C:\Users\ferry\.ssh\id_rsa", "absolute_path"),
        ("C:secret.py", "drive_qualified_path"),
    ],
)
def test_run_rejects_workspace_file_traversal_and_absolute_paths(
    client: TestClient,
    unsafe_path: str,
    expected_code: str,
) -> None:
    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(
            files=[{"path": unsafe_path, "content": "print('safe')\n"}],
            git_diff=None,
        ),
    )

    assert response.status_code == 400
    body = response.json()
    assert_error_response(body, expected_code)
    assert_not_serialized(body, "print('safe')")


def test_run_rejects_selection_path_traversal_when_selection_mode_is_allowed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = backend_rbac_capability().model_copy(
        update={"input_modes": ["selection"]},
    )
    use_capability(monkeypatch, capability)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(
            files=[],
            git_diff=None,
            selection={
                "path": "src/../../secret.py",
                "start_line": 1,
                "end_line": 1,
                "content": "print('selection')\n",
            },
        ),
    )

    assert response.status_code == 400
    body = response.json()
    assert_error_response(body, "path_traversal")
    assert_not_serialized(body, "print('selection')")


def test_run_normalizes_safe_workspace_relative_paths_before_runner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_paths: list[str] = []

    class PathRecordingRunner:
        def run(self, _capability: Any, _request: Any, workspace_files: Any) -> dict[str, Any]:
            observed_paths.extend(file.path for file in workspace_files)
            return public_result()

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: PathRecordingRunner(),
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(
            files=[
                {
                    "path": ".\\src\\..\\src\\app.py",
                    "content": "print('normalized')\n",
                }
            ],
            git_diff=None,
        ),
    )

    assert response.status_code == 200
    assert observed_paths == ["src/app.py"]
