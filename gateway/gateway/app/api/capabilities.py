from fastapi import APIRouter, HTTPException

from ..capabilities.registry import default_registry

router = APIRouter(prefix="/v1")


@router.get("/capabilities")
def list_capabilities() -> dict[str, list[dict]]:
    registry = default_registry()
    return {"capabilities": registry.list_public()}


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    return capability.public_view()
