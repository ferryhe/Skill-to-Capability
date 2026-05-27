import pytest

from gateway.app.security.input_policy import (
    InputPolicy,
    InputPolicyViolation,
    WorkspaceInputFile,
    validate_workspace_context_files,
)
from gateway.app.security.path_policy import normalize_workspace_relative_path


DEFAULT_POLICY = InputPolicy(
    max_files=3,
    max_total_input_bytes=30,
    deny_file_globs=["**/.env", "**/*.pem", "**/id_rsa"],
)


def assert_policy_violation(
    files: list[WorkspaceInputFile],
    expected_code: str,
) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(files, DEFAULT_POLICY)

    assert exc_info.value.code == expected_code
    assert expected_code in str(exc_info.value)


def test_input_policy_violation_preserves_standard_exception_message_args() -> None:
    violation = InputPolicyViolation(
        code="policy_error",
        message="Readable policy error",
    )

    assert violation.code == "policy_error"
    assert violation.message == "Readable policy error"
    assert violation.args == ("Readable policy error",)
    assert str(violation) == "policy_error: Readable policy error"


def test_normalizes_safe_workspace_relative_paths_to_posix_separators() -> None:
    assert normalize_workspace_relative_path("src\\app.py") == "src/app.py"
    assert normalize_workspace_relative_path("./src/../src/app.py") == "src/app.py"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../escape.py",
        "src/../../escape.py",
    ],
)
def test_rejects_parent_directory_escape_paths(unsafe_path: str) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        normalize_workspace_relative_path(unsafe_path)

    assert exc_info.value.code == "path_traversal"
    assert unsafe_path in str(exc_info.value)


@pytest.mark.parametrize(
    "absolute_path",
    [
        "/etc/passwd",
        "C:/Users/ferry/.ssh/id_rsa",
        "C:\\Users\\ferry\\.ssh\\id_rsa",
    ],
)
def test_rejects_absolute_paths(absolute_path: str) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        normalize_workspace_relative_path(absolute_path)

    assert exc_info.value.code == "absolute_path"
    assert absolute_path in str(exc_info.value)


@pytest.mark.parametrize(
    "drive_qualified_path",
    [
        "C:secret.txt",
        "C:../secret.txt",
    ],
)
def test_rejects_windows_drive_qualified_paths(drive_qualified_path: str) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        normalize_workspace_relative_path(drive_qualified_path)

    assert exc_info.value.code == "drive_qualified_path"
    assert drive_qualified_path in str(exc_info.value)


@pytest.mark.parametrize(
    "denied_path",
    [
        ".env",
        "service/.env",
        "certs/client.pem",
        "id_rsa",
        "keys/id_rsa",
    ],
)
def test_rejects_denylisted_file_globs(denied_path: str) -> None:
    assert_policy_violation(
        [WorkspaceInputFile(path=denied_path, content="not relevant")],
        "denylisted_file",
    )


@pytest.mark.parametrize(
    "denied_path",
    [
        ".env",
        "client.pem",
        "private.key",
        "id_rsa",
        "credentials.json",
    ],
)
def test_input_policy_default_rejects_standard_secret_file_denylist(
    denied_path: str,
) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(
            [WorkspaceInputFile(path=denied_path, content="not relevant")],
            InputPolicy(),
        )

    assert exc_info.value.code == "denylisted_file"
    assert denied_path in str(exc_info.value)


@pytest.mark.parametrize(
    "denied_path",
    [
        "SERVICE/.ENV",
        "certs/CLIENT.PEM",
        "keys/ID_RSA",
        "config/CREDENTIALS.JSON",
    ],
)
def test_rejects_denylisted_file_globs_case_insensitively(denied_path: str) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(
            [WorkspaceInputFile(path=denied_path, content="not relevant")],
            InputPolicy(),
        )

    assert exc_info.value.code == "denylisted_file"
    assert denied_path in str(exc_info.value)


def test_rejects_context_when_file_count_exceeds_policy_limit() -> None:
    files = [
        WorkspaceInputFile(path="a.py", content="a"),
        WorkspaceInputFile(path="b.py", content="b"),
        WorkspaceInputFile(path="c.py", content="c"),
        WorkspaceInputFile(path="d.py", content="d"),
    ]

    assert_policy_violation(files, "max_files_exceeded")


def test_rejects_context_when_total_input_bytes_exceeds_policy_limit() -> None:
    files = [
        WorkspaceInputFile(path="a.py", content="1234567890"),
        WorkspaceInputFile(path="b.py", content="1234567890"),
        WorkspaceInputFile(path="c.py", content="12345678901"),
    ]

    assert_policy_violation(files, "max_total_input_bytes_exceeded")


def test_rejects_oversized_secret_like_content_before_secret_scanning() -> None:
    files = [
        WorkspaceInputFile(
            path="src/settings.py",
            content='OPENAI_API_KEY = "sk-proj-secretvalue"',
        )
    ]

    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(
            files,
            InputPolicy(max_total_input_bytes=10),
        )

    assert exc_info.value.code == "max_total_input_bytes_exceeded"


def test_rejects_secret_like_content_fail_closed() -> None:
    files = [
        WorkspaceInputFile(
            path="src/settings.py",
            content='OPENAI_API_KEY = "sk-proj-secretvalue"',
        )
    ]

    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(
            files,
            InputPolicy(max_total_input_bytes=100),
        )

    assert exc_info.value.code == "secret_like_content"


@pytest.mark.parametrize(
    "content",
    [
        'AWS_SECRET_ACCESS_KEY: "very-secret-value"',
        '{"password": "very-secret-value"}',
        "Authorization: Bearer very-secret-value",
    ],
)
def test_rejects_structured_secret_like_content_fail_closed(content: str) -> None:
    with pytest.raises(InputPolicyViolation) as exc_info:
        validate_workspace_context_files(
            [WorkspaceInputFile(path="src/settings.py", content=content)],
            InputPolicy(),
        )

    assert exc_info.value.code == "secret_like_content"
    assert "src/settings.py" in str(exc_info.value)


def test_returns_normalized_files_when_context_satisfies_policy() -> None:
    files = [
        WorkspaceInputFile(path="src\\app.py", content="print('hello')"),
        WorkspaceInputFile(path="./README.md", content="# Docs"),
    ]

    accepted = validate_workspace_context_files(files, DEFAULT_POLICY)

    assert [file.path for file in accepted] == ["src/app.py", "README.md"]
    assert [file.content for file in accepted] == ["print('hello')", "# Docs"]
