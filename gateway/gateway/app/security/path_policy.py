import posixpath
import re

from gateway.app.security.errors import InputPolicyViolation


WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
WINDOWS_DRIVE_QUALIFIED_PATH = re.compile(r"^[A-Za-z]:")


def normalize_workspace_relative_path(path: str) -> str:
    raw_path = path.strip()
    posix_path = raw_path.replace("\\", "/")

    if posix_path.startswith("/") or WINDOWS_ABSOLUTE_PATH.match(raw_path):
        raise InputPolicyViolation(
            code="absolute_path",
            message=f"Absolute workspace file paths are not allowed: {path}",
        )

    if WINDOWS_DRIVE_QUALIFIED_PATH.match(raw_path):
        raise InputPolicyViolation(
            code="drive_qualified_path",
            message=f"Windows drive-qualified workspace file paths are not allowed: {path}",
        )

    normalized = posixpath.normpath(posix_path)
    if normalized == ".":
        raise InputPolicyViolation(
            code="invalid_path",
            message=f"Workspace file path must name a file: {path}",
        )

    if normalized == ".." or normalized.startswith("../"):
        raise InputPolicyViolation(
            code="path_traversal",
            message=f"Workspace file path escapes the workspace: {path}",
        )

    return normalized
