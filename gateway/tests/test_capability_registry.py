from pathlib import Path

import pytest

from gateway.app.capabilities.registry import (
    CapabilityRegistry,
    ManifestLoadError,
    default_registry,
)


CAPABILITIES_DIR = Path(__file__).resolve().parents[1] / "capabilities"


VALID_MANIFEST = """
id: {capability_id}
name: Backend RBAC Review
version: 0.1.0
category: code-review
visible_description: Review backend RBAC and public API payload boundaries.
input_modes:
{input_modes}
input_schema:
  type: object
output_schema:
  type: object
client_permissions:
  reads_workspace: true
  writes_workspace: optional
  runs_commands: optional
  sends_code_to_server: true
approval_policy:
  upload_context: user_confirm_large
  apply_patch: user_confirm
  run_commands: user_confirm
internal:
  skill_ref: backend-rbac-review
  runner: hermes
  expose_skill_text: false
"""


def write_manifest(
    directory: Path,
    filename: str,
    capability_id: str,
    input_modes: list[str] | None = None,
) -> None:
    modes = input_modes or ["current_file", "selected_files"]
    rendered_modes = "\n".join(f"  - {mode}" for mode in modes)
    (directory / filename).write_text(
        VALID_MANIFEST.format(
            capability_id=capability_id,
            input_modes=rendered_modes,
        ),
        encoding="utf-8",
    )


def test_registry_loads_manifest_and_returns_public_view_without_internal_fields() -> None:
    registry = CapabilityRegistry.from_directory(CAPABILITIES_DIR)

    capability = registry.get("backend-rbac-review")
    public_view = capability.public_view()

    assert public_view["id"] == "backend-rbac-review"
    assert public_view["name"] == "Backend RBAC Review"
    assert public_view["security"]["max_files"] == 20
    assert "internal" not in public_view
    assert "skill_ref" not in str(public_view)
    assert "model_policy" not in str(public_view)


def test_registry_lists_public_capabilities() -> None:
    registry = CapabilityRegistry.from_directory(CAPABILITIES_DIR)

    public_capabilities = registry.list_public()

    assert [capability["id"] for capability in public_capabilities] == [
        "backend-rbac-review"
    ]
    assert "internal" not in str(public_capabilities)
    assert "skill_ref" not in str(public_capabilities)
    assert "model_policy" not in str(public_capabilities)


def test_invalid_manifest_load_raises_clear_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "broken.yaml"
    manifest_path.write_text(
        """
id: broken-capability
name: Broken Capability
version: 0.1.0
visible_description: Missing required manifest fields.
input_modes:
  - current_file
internal:
  skill_ref: broken
  runner: hermes
  expose_skill_text: true
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestLoadError, match="broken.yaml"):
        CapabilityRegistry.from_directory(tmp_path)


def test_duplicate_capability_ids_raise_registry_load_error(tmp_path: Path) -> None:
    write_manifest(tmp_path, "first.yaml", "duplicate-capability")
    write_manifest(tmp_path, "second.yaml", "duplicate-capability")

    with pytest.raises(ManifestLoadError, match="duplicate capability id"):
        CapabilityRegistry.from_directory(tmp_path)


def test_duplicate_input_modes_raise_manifest_load_error(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        "duplicate-input-modes.yaml",
        "duplicate-input-modes",
        input_modes=["current_file", "current_file"],
    )

    with pytest.raises(ManifestLoadError, match="input_modes"):
        CapabilityRegistry.from_directory(tmp_path)


def test_missing_manifest_directory_raises_clear_error(tmp_path: Path) -> None:
    missing_dir = tmp_path / "does-not-exist"

    with pytest.raises(ManifestLoadError, match="does not exist"):
        CapabilityRegistry.from_directory(missing_dir)


def test_empty_manifest_directory_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestLoadError, match="No capability manifests found"):
        CapabilityRegistry.from_directory(tmp_path)


def test_default_registry_returns_cached_registry() -> None:
    first_registry = default_registry()
    second_registry = default_registry()

    assert first_registry is second_registry
