from gateway.app.auth.models import RequestIdentity

from .models import CapabilityRunRequest
from .store import TaskRecord, task_store


def is_async_requested(request: CapabilityRunRequest) -> bool:
    if request.options is None:
        return False
    return request.options.get("async") is True or (
        request.options.get("execution_mode") == "async"
    )


def enqueue_capability_run(
    capability_id: str,
    owner_identity: RequestIdentity,
    input_metadata: dict | None = None,
) -> TaskRecord:
    return task_store.create_queued(capability_id, owner_identity, input_metadata)
