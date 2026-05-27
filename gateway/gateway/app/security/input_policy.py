from dataclasses import dataclass, field
from fnmatch import fnmatchcase
import re

from gateway.app.security.errors import InputPolicyViolation
from gateway.app.security.path_policy import normalize_workspace_relative_path


SECRET_LIKE_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\b[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\b\s*[:=]",
        re.I,
    ),
    re.compile(r'"(?:password|secret|token|api_key)"\s*:', re.I),
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S+", re.I),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{8,}"),
)

DEFAULT_DENY_FILE_GLOBS = [
    "**/.env",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/credentials.json",
]


@dataclass(frozen=True)
class WorkspaceInputFile:
    path: str
    content: str
    sha256: str | None = None


@dataclass(frozen=True)
class InputPolicy:
    max_files: int | None = None
    max_total_input_bytes: int | None = None
    deny_file_globs: list[str] = field(
        default_factory=lambda: list(DEFAULT_DENY_FILE_GLOBS)
    )


def validate_workspace_context_files(
    files: list[WorkspaceInputFile],
    policy: InputPolicy,
) -> list[WorkspaceInputFile]:
    if policy.max_files is not None and len(files) > policy.max_files:
        raise InputPolicyViolation(
            code="max_files_exceeded",
            message=f"Workspace context has {len(files)} files; limit is {policy.max_files}",
        )

    accepted: list[WorkspaceInputFile] = []
    total_bytes = 0
    for file in files:
        normalized_path = normalize_workspace_relative_path(file.path)
        _reject_denylisted_file(normalized_path, policy.deny_file_globs or [])
        _reject_secret_like_content(normalized_path, file.content)

        total_bytes += len(file.content.encode("utf-8"))
        if (
            policy.max_total_input_bytes is not None
            and total_bytes > policy.max_total_input_bytes
        ):
            raise InputPolicyViolation(
                code="max_total_input_bytes_exceeded",
                message=(
                    f"Workspace context is {total_bytes} bytes; "
                    f"limit is {policy.max_total_input_bytes}"
                ),
            )

        accepted.append(
            WorkspaceInputFile(
                path=normalized_path,
                content=file.content,
                sha256=file.sha256,
            )
        )

    return accepted


def _reject_denylisted_file(path: str, deny_file_globs: list[str]) -> None:
    comparable_path = path.lower()
    for pattern in deny_file_globs:
        normalized_pattern = pattern.replace("\\", "/").lower()
        root_pattern = normalized_pattern.removeprefix("**/")
        if fnmatchcase(comparable_path, normalized_pattern) or fnmatchcase(
            comparable_path, root_pattern
        ):
            raise InputPolicyViolation(
                code="denylisted_file",
                message=f"Workspace file is denied by policy: {path}",
            )


def _reject_secret_like_content(path: str, content: str) -> None:
    for pattern in SECRET_LIKE_CONTENT_PATTERNS:
        if pattern.search(content):
            raise InputPolicyViolation(
                code="secret_like_content",
                message=f"Workspace file contains secret-like content: {path}",
            )
