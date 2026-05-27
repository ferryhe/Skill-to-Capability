import importlib
from pathlib import Path

import pytest
import yaml

from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import load_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_SKILL = REPO_ROOT / "examples" / "skills" / "backend-rbac-review" / "SKILL.md"
BODY_ONLY_PHRASE = "BODY ONLY PHRASE THAT MUST NOT LEAK"


def frontmatter_module():
    try:
        return importlib.import_module("gateway.app.skills.frontmatter")
    except ModuleNotFoundError as exc:
        pytest.fail(f"skill frontmatter module is missing: {exc}")


def converter_module():
    try:
        return importlib.import_module("gateway.app.skills.converter")
    except ModuleNotFoundError as exc:
        pytest.fail(f"skill converter module is missing: {exc}")


def valid_skill_text() -> str:
    return f"""---
name: backend-rbac-review
description: Review backend RBAC and public API payload boundaries.
tags: [code-review, security, rbac]
required_environment_variables:
  - GITHUB_TOKEN
required_commands:
  - git
---

# Private Skill Body

{BODY_ONLY_PHRASE}
"""


def as_manifest(value: object) -> CapabilityManifest:
    if isinstance(value, CapabilityManifest):
        return value
    return CapabilityManifest.model_validate(value)


def test_valid_skill_frontmatter_parses_metadata_and_body_separately() -> None:
    frontmatter = frontmatter_module()

    document = frontmatter.parse_skill_frontmatter(valid_skill_text())

    assert document.metadata == {
        "name": "backend-rbac-review",
        "description": "Review backend RBAC and public API payload boundaries.",
        "tags": ["code-review", "security", "rbac"],
        "required_environment_variables": ["GITHUB_TOKEN"],
        "required_commands": ["git"],
    }
    assert BODY_ONLY_PHRASE in document.body
    assert "tags: [code-review, security, rbac]" not in document.body


def test_missing_frontmatter_raises_clear_error_without_body_leak() -> None:
    frontmatter = frontmatter_module()
    text = f"# Skill Body\n\n{BODY_ONLY_PHRASE}\n"

    with pytest.raises(frontmatter.SkillFrontmatterError, match="frontmatter") as exc_info:
        frontmatter.parse_skill_frontmatter(text)

    assert BODY_ONLY_PHRASE not in str(exc_info.value)


def test_malformed_frontmatter_raises_clear_error_without_body_leak() -> None:
    frontmatter = frontmatter_module()
    text = f"""---
name: [unterminated
---

{BODY_ONLY_PHRASE}
"""

    with pytest.raises(frontmatter.SkillFrontmatterError, match="frontmatter") as exc_info:
        frontmatter.parse_skill_frontmatter(text)

    assert BODY_ONLY_PHRASE not in str(exc_info.value)


def test_converter_output_validates_as_capability_manifest() -> None:
    converter = converter_module()

    manifest = as_manifest(converter.convert_skill_to_capability_manifest(valid_skill_text()))

    assert manifest.id == "backend-rbac-review"
    assert manifest.visible_description == "Review backend RBAC and public API payload boundaries."
    assert manifest.category == "code-review"
    assert manifest.input_modes == ["current_file", "selected_files", "git_diff"]
    assert manifest.input_schema["required"] == ["instruction"]
    assert manifest.input_schema["properties"]["files"]["maxItems"] == 20
    assert manifest.input_schema["properties"]["diff"]["maxLength"] == 200000
    assert manifest.output_schema["required"] == ["summary"]
    assert "safe_rationale" in manifest.output_schema["properties"]
    assert manifest.client_permissions.reads_workspace is True
    assert manifest.client_permissions.writes_workspace == "optional"
    assert manifest.client_permissions.runs_commands == "optional"
    assert manifest.approval_policy.upload_context == "user_confirm_large"
    assert manifest.approval_policy.apply_patch == "user_confirm"
    assert manifest.approval_policy.run_commands == "user_confirm"
    assert manifest.security is not None
    assert manifest.security.max_files == 20
    assert "**/.env" in (manifest.security.deny_file_globs or [])


def test_converter_uses_canonical_deny_file_globs_without_sharing_manifest_list() -> None:
    converter = converter_module()
    input_policy = importlib.import_module("gateway.app.security.input_policy")
    marker_glob = "**/temporary-canonical-deny-marker"
    next_marker_glob = "**/post-conversion-deny-marker"

    input_policy.DEFAULT_DENY_FILE_GLOBS.append(marker_glob)
    try:
        manifest = as_manifest(converter.convert_skill_to_capability_manifest(valid_skill_text()))
        deny_file_globs = manifest.security.deny_file_globs if manifest.security else None

        assert deny_file_globs is not None
        assert deny_file_globs == input_policy.DEFAULT_DENY_FILE_GLOBS
        assert deny_file_globs is not input_policy.DEFAULT_DENY_FILE_GLOBS

        input_policy.DEFAULT_DENY_FILE_GLOBS.append(next_marker_glob)
        assert next_marker_glob not in deny_file_globs
    finally:
        input_policy.DEFAULT_DENY_FILE_GLOBS.remove(marker_glob)
        if next_marker_glob in input_policy.DEFAULT_DENY_FILE_GLOBS:
            input_policy.DEFAULT_DENY_FILE_GLOBS.remove(next_marker_glob)


def test_converter_sets_internal_skill_ref_and_never_exposes_skill_text() -> None:
    converter = converter_module()

    manifest = as_manifest(converter.convert_skill_to_capability_manifest(valid_skill_text()))

    assert manifest.internal.skill_ref == "backend-rbac-review"
    assert manifest.internal.expose_skill_text is False
    assert manifest.internal.runner == "hermes"
    assert manifest.internal.required_env == ["GITHUB_TOKEN"]
    assert manifest.internal.required_commands == ["git"]


@pytest.mark.parametrize("field", ["name", "description"])
def test_converter_requires_public_frontmatter_fields_without_body_leak(field: str) -> None:
    converter = converter_module()
    metadata = {
        "name": "backend-rbac-review",
        "description": "Review backend RBAC and public API payload boundaries.",
    }
    del metadata[field]
    text = f"""---
{yaml.safe_dump(metadata, sort_keys=False)}---

{BODY_ONLY_PHRASE}
"""

    with pytest.raises(converter.SkillFrontmatterError, match=field) as exc_info:
        converter.convert_skill_to_capability_manifest(text)

    assert BODY_ONLY_PHRASE not in str(exc_info.value)


def test_serialized_converter_output_does_not_contain_skill_body_text() -> None:
    converter = converter_module()

    manifest = as_manifest(converter.convert_skill_to_capability_manifest(valid_skill_text()))

    assert BODY_ONLY_PHRASE not in manifest.model_dump_json()
    assert BODY_ONLY_PHRASE not in str(manifest.public_view())


def test_generated_manifest_yaml_can_be_loaded_by_registry(
    tmp_path: Path,
) -> None:
    converter = converter_module()
    manifest = as_manifest(converter.convert_skill_to_capability_manifest(valid_skill_text()))
    manifest_path = tmp_path / "backend-rbac-review.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )

    loaded_manifest = load_manifest(manifest_path)

    assert loaded_manifest.id == "backend-rbac-review"
    assert loaded_manifest.internal.skill_ref == "backend-rbac-review"
    assert BODY_ONLY_PHRASE not in loaded_manifest.model_dump_json()


def test_example_skill_converts_successfully_without_body_text() -> None:
    converter = converter_module()
    skill_text = EXAMPLE_SKILL.read_text(encoding="utf-8")

    manifest = as_manifest(converter.convert_skill_to_capability_manifest(skill_text))

    assert manifest.id == "backend-rbac-review"
    assert manifest.internal.skill_ref == "backend-rbac-review"
    assert manifest.internal.expose_skill_text is False
    assert (
        "Real private skills should live only in the Skill Gateway private skill registry"
        not in manifest.model_dump_json()
    )
