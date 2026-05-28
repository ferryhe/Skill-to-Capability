from fastapi import APIRouter, Depends

from .errors import api_error
from ..auth.dependencies import require_request_identity
from ..auth.models import RequestIdentity
from ..capabilities.manifest import SecurityPolicy
from ..capabilities.policy import can_run_capability, is_capability_visible
from ..capabilities.registry import default_registry
from ..runners.base import CapabilityRunner
from ..runners.hermes_runner import HermesCapabilityRunner, HermesRunnerError
from ..runners.mock_runner import MockCapabilityRunner
from ..security.input_policy import (
    InputPolicy,
    InputPolicyViolation,
    WorkspaceInputFile,
    WorkspaceInputText,
    validate_workspace_context_inputs,
)
from ..security.output_filter import filter_capability_run_result
from ..tasks.models import (
    CapabilityRunRequest,
    CapabilityTaskQueued,
    CapabilityTaskResult,
    WorkspaceSelection,
)
from ..tasks.queue import enqueue_capability_run, is_async_requested
from ..tasks.store import task_store

router = APIRouter(prefix="/v1")

FILE_LIKE_INPUT_MODES = {"current_file", "selected_files", "workspace_snapshot"}


@router.get("/capabilities")
def list_capabilities(
    identity: RequestIdentity = Depends(require_request_identity),
) -> dict[str, list[dict]]:
    registry = default_registry()
    return {
        "capabilities": [
            capability.public_view()
            for capability in registry.list_all()
            if is_capability_visible(capability, identity)
        ]
    }


@router.get("/capabilities/{capability_id}")
def get_capability(
    capability_id: str,
    identity: RequestIdentity = Depends(require_request_identity),
) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None or not is_capability_visible(capability, identity):
        raise api_error(
            status_code=404,
            code="capability_not_found",
            message="Capability not found",
        )
    return capability.public_view()


@router.post("/capabilities/{capability_id}/run")
def run_capability(
    capability_id: str,
    request: CapabilityRunRequest,
    identity: RequestIdentity = Depends(require_request_identity),
) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None or not is_capability_visible(capability, identity):
        raise api_error(
            status_code=404,
            code="capability_not_found",
            message="Capability not found",
        )
    if not can_run_capability(capability, identity):
        raise api_error(
            status_code=403,
            code="capability_forbidden",
            message="Capability is not available for this identity.",
        )

    _validate_selection_range(request)
    _validate_request_input_modes(capability.input_modes, request)
    workspace_files = _workspace_files_from_request(request)
    text_inputs = _text_inputs_from_request(request)
    audit_input_metadata = _audit_input_metadata(request)
    try:
        validated_files = validate_workspace_context_inputs(
            workspace_files,
            text_inputs,
            _input_policy_from_security(capability.security),
        )
    except InputPolicyViolation as exc:
        raise api_error(
            status_code=400,
            code=exc.code,
            message=exc.message,
        ) from exc

    if is_async_requested(request):
        task = enqueue_capability_run(
            capability.id,
            identity,
            audit_input_metadata,
        )
        return CapabilityTaskQueued(
            task_id=task.task_id,
            status="queued",
        ).model_dump()

    runner = _runner_for_capability(capability.internal.runner)
    runner_error_message: str | None = None
    try:
        raw_result = runner.run(capability, request, validated_files)
    except HermesRunnerError as exc:
        runner_error_message = str(exc)

    if runner_error_message is not None:
        raise api_error(
            status_code=502,
            code="hermes_runner_error",
            message=runner_error_message,
        )
    result = filter_capability_run_result(raw_result)
    task = task_store.create_completed(
        capability.id,
        result,
        identity,
        input_metadata=audit_input_metadata,
        output_metadata=_audit_output_metadata(result),
    )
    task_result = CapabilityTaskResult(
        task_id=task.task_id,
        status="completed",
        result=result,
    )
    return task_result.model_dump()


def _validate_selection_range(request: CapabilityRunRequest) -> None:
    if request.workspace is None or request.workspace.selection is None:
        return

    selection = request.workspace.selection
    if _selection_range_is_invalid(selection):
        raise api_error(
            status_code=400,
            code="invalid_selection_range",
            message=(
                "Selection start_line and end_line must be provided together, "
                "be at least 1, and end_line must be greater than or equal "
                "to start_line."
            ),
        )


def _selection_range_is_invalid(selection: WorkspaceSelection) -> bool:
    if (selection.start_line is None) != (selection.end_line is None):
        return True
    if selection.start_line is None or selection.end_line is None:
        return False
    if selection.start_line < 1 or selection.end_line < 1:
        return True
    return selection.end_line < selection.start_line


def _validate_request_input_modes(
    input_modes: list[str],
    request: CapabilityRunRequest,
) -> None:
    if request.workspace is None:
        return

    declared_modes = set(input_modes)
    if request.workspace.selection is not None and "selection" not in declared_modes:
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept selection input.",
        )

    if request.workspace.git_diff is not None and "git_diff" not in declared_modes:
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept git_diff input.",
        )

    if request.workspace.files and not declared_modes.intersection(FILE_LIKE_INPUT_MODES):
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept workspace files input.",
        )


def _runner_for_capability(runner_name: str) -> CapabilityRunner:
    if runner_name == "mock":
        return MockCapabilityRunner()
    if runner_name == "hermes":
        return HermesCapabilityRunner()
    raise api_error(
        status_code=501,
        code="unsupported_runner",
        message="Capability runner is not supported by this Gateway.",
    )


def _workspace_files_from_request(
    request: CapabilityRunRequest,
) -> list[WorkspaceInputFile]:
    if request.workspace is None:
        return []
    files = [
        WorkspaceInputFile(
            path=file.path,
            content=file.content,
            sha256=file.sha256,
        )
        for file in request.workspace.files
    ]
    if request.workspace.selection is not None:
        files.append(
            WorkspaceInputFile(
                path=request.workspace.selection.path,
                content=request.workspace.selection.content,
            )
        )
    return files


def _text_inputs_from_request(
    request: CapabilityRunRequest,
) -> list[WorkspaceInputText]:
    if request.workspace is None or request.workspace.git_diff is None:
        return []
    return [
        WorkspaceInputText(
            label="workspace.git_diff",
            content=request.workspace.git_diff,
        )
    ]


def _audit_input_metadata(request: CapabilityRunRequest) -> dict[str, object]:
    workspace = request.workspace
    files = workspace.files if workspace is not None else []
    git_diff = workspace.git_diff if workspace is not None else None
    selection = workspace.selection if workspace is not None else None
    return {
        "execution_mode": "async" if is_async_requested(request) else "sync",
        "instruction_length": len(request.instruction),
        "workspace_file_count": len(files),
        "workspace_file_bytes": sum(_text_size(file.content) for file in files),
        "has_git_diff": git_diff is not None,
        "git_diff_bytes": _text_size(git_diff),
        "has_selection": selection is not None,
        "selection_bytes": _text_size(selection.content if selection else None),
        "option_count": len(request.options or {}),
        "client_type": request.client.type if request.client is not None else None,
    }


def _audit_output_metadata(result: object) -> dict[str, object]:
    if not hasattr(result, "model_dump"):
        return {"status": "completed"}
    dumped = result.model_dump(mode="json")
    return {
        "status": "completed",
        "result_keys": sorted(dumped.keys()),
        "finding_count": len(getattr(result, "findings", [])),
        "artifact_count": len(getattr(result, "artifacts", [])),
        "recommended_test_count": len(getattr(result, "recommended_tests", [])),
        "patch_present": getattr(result, "patch", None) is not None,
        "result_size_bytes": len(result.model_dump_json().encode("utf-8")),
    }


def _text_size(value: str | None) -> int:
    if value is None:
        return 0
    return len(value.encode("utf-8"))


def _input_policy_from_security(security: SecurityPolicy | None) -> InputPolicy:
    default_policy = InputPolicy()
    if security is None:
        return default_policy

    return InputPolicy(
        max_files=security.max_files,
        max_total_input_bytes=security.max_total_input_bytes,
        deny_file_globs=(
            security.deny_file_globs
            if security.deny_file_globs is not None
            else default_policy.deny_file_globs
        ),
        allow_file_globs=security.allow_file_globs,
    )
