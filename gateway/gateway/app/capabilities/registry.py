from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .manifest import CapabilityManifest

DEV_RUNNER_ENV = "SKILL_GATEWAY_DEV_RUNNER"
DEV_RUNNER_OVERRIDES = {"mock"}
AUTH_MODE_ENV = "SKILL_GATEWAY_AUTH_MODE"
AUTH_DISABLED_ENV = "SKILL_GATEWAY_AUTH_DISABLED"


class ManifestLoadError(ValueError):
    """Raised when a capability manifest cannot be loaded or validated."""


class CapabilityRegistry:
    def __init__(self, manifests: list[CapabilityManifest]) -> None:
        self._manifests: dict[str, CapabilityManifest] = {}
        for manifest in manifests:
            if manifest.id in self._manifests:
                raise ManifestLoadError(f"duplicate capability id: {manifest.id}")
            self._manifests[manifest.id] = manifest

    @classmethod
    def from_directory(cls, directory: Path) -> "CapabilityRegistry":
        if not directory.exists():
            raise ManifestLoadError(f"Capability manifest directory does not exist: {directory}")
        if not directory.is_dir():
            raise ManifestLoadError(f"Capability manifest path is not a directory: {directory}")

        manifest_paths = sorted(
            [*directory.glob("*.yaml"), *directory.glob("*.yml")]
        )
        if not manifest_paths:
            raise ManifestLoadError(f"No capability manifests found in {directory}")

        manifests = [load_manifest(path) for path in manifest_paths]
        return cls(manifests)

    def get(self, capability_id: str) -> CapabilityManifest:
        return self._manifests[capability_id]

    def find(self, capability_id: str) -> CapabilityManifest | None:
        return self._manifests.get(capability_id)

    def list_all(self) -> list[CapabilityManifest]:
        return list(self._manifests.values())

    def list_public(self) -> list[dict[str, Any]]:
        return [manifest.public_view() for manifest in self._manifests.values()]


def load_manifest(path: Path) -> CapabilityManifest:
    try:
        raw_manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestLoadError(f"Failed to parse capability manifest {path}: {exc}") from exc
    except OSError as exc:
        raise ManifestLoadError(f"Failed to read capability manifest {path}: {exc}") from exc

    if not isinstance(raw_manifest, dict):
        raise ManifestLoadError(f"Capability manifest {path} must be a YAML object")

    try:
        return CapabilityManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        raise ManifestLoadError(
            f"Capability manifest {path} failed validation: {exc}"
        ) from exc


@lru_cache(maxsize=1)
def default_registry() -> CapabilityRegistry:
    capabilities_dir = Path(__file__).resolve().parents[3] / "capabilities"
    registry = CapabilityRegistry.from_directory(capabilities_dir)
    return _with_dev_runner_override(registry)


def _with_dev_runner_override(registry: CapabilityRegistry) -> CapabilityRegistry:
    runner = os.getenv(DEV_RUNNER_ENV, "").strip().casefold()
    if not runner:
        return registry
    if not _dev_auth_bypass_enabled():
        raise ManifestLoadError(
            f"{DEV_RUNNER_ENV} requires {AUTH_MODE_ENV}=dev or "
            f"{AUTH_DISABLED_ENV}=true."
        )
    if runner not in DEV_RUNNER_OVERRIDES:
        raise ManifestLoadError(
            f"{DEV_RUNNER_ENV} only supports: "
            + ", ".join(sorted(DEV_RUNNER_OVERRIDES))
        )

    manifests = [
        manifest.model_copy(
            update={"internal": manifest.internal.model_copy(update={"runner": runner})}
        )
        for manifest in registry.list_all()
    ]
    return CapabilityRegistry(manifests)


def _dev_auth_bypass_enabled() -> bool:
    auth_mode = os.getenv(AUTH_MODE_ENV, "").strip().casefold()
    auth_disabled = os.getenv(AUTH_DISABLED_ENV, "").strip().casefold()
    return auth_mode == "dev" or auth_disabled == "true"
