import json
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.security.input_policy import WorkspaceInputFile
from gateway.app.tasks.models import CapabilityRunRequest, CapabilityRunResult

from .json_output import HermesRunnerError, parse_runner_json_output


PROCESS_FAILED_MESSAGE = "Hermes runner process failed."
PROCESS_TIMEOUT_MESSAGE = "Hermes runner process timed out."
PROCESS_START_FAILED_MESSAGE = "Hermes runner process could not be started."

RunProcess = Callable[..., subprocess.CompletedProcess[str]]


class HermesCapabilityRunner:
    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        run_process: RunProcess | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self._command = tuple(command) if command is not None else None
        self._run_process = run_process or subprocess.run
        self._timeout_seconds = timeout_seconds

    def run(
        self,
        capability: CapabilityManifest,
        request: CapabilityRunRequest,
        workspace_files: Sequence[WorkspaceInputFile],
    ) -> CapabilityRunResult:
        command = self._command_for(capability)
        payload = _runner_payload(capability, request, workspace_files)

        process_error_message: str | None = None
        try:
            completed_process = self._run_process(
                command,
                input=json.dumps(payload, separators=(",", ":")),
                text=True,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            process_error_message = PROCESS_TIMEOUT_MESSAGE
        except OSError:
            process_error_message = PROCESS_START_FAILED_MESSAGE

        if process_error_message is not None:
            raise HermesRunnerError(process_error_message)

        if completed_process.returncode != 0:
            raise HermesRunnerError(PROCESS_FAILED_MESSAGE)

        return parse_runner_json_output(completed_process.stdout)

    def _command_for(self, capability: CapabilityManifest) -> tuple[str, ...]:
        if self._command is not None:
            return self._command
        return (
            "hermes",
            "run",
            "--skill",
            capability.internal.skill_ref,
            "--json",
        )


def _runner_payload(
    capability: CapabilityManifest,
    request: CapabilityRunRequest,
    workspace_files: Sequence[WorkspaceInputFile],
) -> dict[str, Any]:
    return {
        "capability": {
            "id": capability.id,
            "name": capability.name,
            "skill_ref": capability.internal.skill_ref,
        },
        "request": request.model_dump(mode="json", exclude_none=True),
        "workspace_files": [
            {
                "path": file.path,
                "content": file.content,
                "sha256": file.sha256,
            }
            for file in workspace_files
        ],
    }
