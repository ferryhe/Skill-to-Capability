from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .manifest import CapabilityManifest


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
        manifests: list[CapabilityManifest] = []
        for path in sorted(directory.glob("*.yaml")):
            manifests.append(load_manifest(path))
        for path in sorted(directory.glob("*.yml")):
            manifests.append(load_manifest(path))
        return cls(manifests)

    def get(self, capability_id: str) -> CapabilityManifest:
        return self._manifests[capability_id]

    def find(self, capability_id: str) -> CapabilityManifest | None:
        return self._manifests.get(capability_id)

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


def default_registry() -> CapabilityRegistry:
    capabilities_dir = Path(__file__).resolve().parents[3] / "capabilities"
    return CapabilityRegistry.from_directory(capabilities_dir)
