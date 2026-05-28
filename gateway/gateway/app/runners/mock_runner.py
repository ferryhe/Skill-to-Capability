from collections.abc import Sequence

from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.security.input_policy import WorkspaceInputFile
from gateway.app.tasks.models import CapabilityRunRequest, CapabilityRunResult

SAMPLE_RBAC_BUG_SNIPPET = (
    "def can_view_admin_report(user: User) -> bool:\n"
    "    # BUG: this grants every active user access to the admin report.\n"
    "    return user.is_active"
)
SAMPLE_RBAC_PATCH = "\n".join(
    [
        "diff --git a/app.py b/app.py",
        "--- a/app.py",
        "+++ b/app.py",
        "@@ -11,3 +11,3 @@",
        " def can_view_admin_report(user: User) -> bool:",
        "-    # BUG: this grants every active user access to the admin report.",
        "-    return user.is_active",
        "+    # Only active administrators may view the admin report.",
        '+    return user.is_active and user.role == "admin"',
        "",
    ]
)
SAMPLE_RBAC_TEST_COMMAND = "python -m unittest discover -s tests -v"
SAMPLE_CAPABILITY_ID = "backend-rbac-review"
SAMPLE_WORKSPACE_NAME = "sample-workspace"


class MockCapabilityRunner:
    def run(
        self,
        capability: CapabilityManifest,
        request: CapabilityRunRequest,
        workspace_files: Sequence[WorkspaceInputFile],
    ) -> CapabilityRunResult:
        file_count = len(workspace_files)
        plural = "" if file_count == 1 else "s"
        patch = _sample_rbac_patch(capability, request, workspace_files)
        return CapabilityRunResult(
            summary=(
                f"Mock review completed for {capability.name}; "
                f"inspected {file_count} workspace file{plural}."
            ),
            findings=(
                [
                    {
                        "severity": "high",
                        "path": "app.py",
                        "line": 13,
                        "title": "Active users bypass admin-only report access",
                        "message": (
                            "The sample RBAC guard checks only whether the user "
                            "is active, so non-admin active users can view the "
                            "admin report."
                        ),
                    }
                ]
                if patch is not None
                else []
            ),
            patch=patch,
            recommended_tests=[
                SAMPLE_RBAC_TEST_COMMAND if patch is not None else "python -m pytest"
            ],
            artifacts=[],
            safe_rationale=(
                "The mock runner returns a public result shape only and does not "
                "execute commands, modify files, or expose private capability data."
            ),
            confidence=0.82,
        )


def _sample_rbac_patch(
    capability: CapabilityManifest,
    request: CapabilityRunRequest,
    workspace_files: Sequence[WorkspaceInputFile],
) -> str | None:
    if not _sample_patch_requested(capability, request):
        return None
    for workspace_file in workspace_files:
        content = workspace_file.content.replace("\r\n", "\n")
        if workspace_file.path == "app.py" and SAMPLE_RBAC_BUG_SNIPPET in content:
            return SAMPLE_RBAC_PATCH
    return None


def _sample_patch_requested(
    capability: CapabilityManifest,
    request: CapabilityRunRequest,
) -> bool:
    if capability.id != SAMPLE_CAPABILITY_ID:
        return False
    if request.options is None:
        return False
    if request.options.get("return_patch") is not True:
        return False
    if request.workspace is None:
        return False
    return request.workspace.name == SAMPLE_WORKSPACE_NAME
