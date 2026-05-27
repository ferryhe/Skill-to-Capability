from collections.abc import Sequence

from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.security.input_policy import WorkspaceInputFile
from gateway.app.tasks.models import CapabilityRunRequest, CapabilityRunResult


class MockCapabilityRunner:
    def run(
        self,
        capability: CapabilityManifest,
        request: CapabilityRunRequest,
        workspace_files: Sequence[WorkspaceInputFile],
    ) -> CapabilityRunResult:
        file_count = len(workspace_files)
        plural = "" if file_count == 1 else "s"
        return CapabilityRunResult(
            summary=(
                f"Mock review completed for {capability.name}; "
                f"inspected {file_count} workspace file{plural}."
            ),
            findings=[],
            patch=None,
            recommended_tests=["python -m pytest"],
            artifacts=[],
            safe_rationale=(
                "The mock runner returns a public result shape only and does not "
                "execute commands, modify files, or expose private capability data."
            ),
            confidence=0.82,
        )
