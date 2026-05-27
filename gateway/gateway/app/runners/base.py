from typing import Protocol, Sequence

from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.security.input_policy import WorkspaceInputFile
from gateway.app.tasks.models import CapabilityRunRequest, CapabilityRunResult


class CapabilityRunner(Protocol):
    def run(
        self,
        capability: CapabilityManifest,
        request: CapabilityRunRequest,
        workspace_files: Sequence[WorkspaceInputFile],
    ) -> CapabilityRunResult:
        """Run a capability against a validated request."""
