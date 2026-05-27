import importlib
import tomllib
from pathlib import Path

import pytest

from gateway.app.capabilities.registry import load_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = Path(__file__).resolve().parents[1]
BODY_ONLY_PHRASE = "PRIVATE CLI BODY THAT MUST NOT LEAK"
PRIVATE_OUTPUT_MARKERS = (
    BODY_ONLY_PHRASE,
    "internal",
    "skill_ref",
    "model_policy",
)


def cli_module():
    try:
        return importlib.import_module("gateway.app.cli")
    except ModuleNotFoundError as exc:
        pytest.fail(f"skillgw CLI module is missing: {exc}")


def write_skill(path: Path) -> None:
    path.write_text(
        f"""---
name: backend-rbac-review
description: Review backend RBAC and public API payload boundaries.
tags: [code-review, security, rbac]
---

# Private Skill Body

{BODY_ONLY_PHRASE}
""",
        encoding="utf-8",
    )


def assert_no_private_markers(text: str) -> None:
    for marker in PRIVATE_OUTPUT_MARKERS:
        assert marker not in text


def test_generate_writes_valid_manifest_without_leaking_skill_body_to_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = cli_module()
    skill_path = tmp_path / "SKILL.md"
    out_path = tmp_path / "backend-rbac-review.yaml"
    write_skill(skill_path)

    exit_code = cli.main(
        [
            "capabilities",
            "generate",
            "--skill",
            str(skill_path),
            "--out",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert out_path.exists()
    manifest_text = out_path.read_text(encoding="utf-8")
    loaded_manifest = load_manifest(out_path)
    assert loaded_manifest.id == "backend-rbac-review"
    assert BODY_ONLY_PHRASE not in manifest_text
    assert_no_private_markers(captured.out)
    assert captured.err == ""


@pytest.mark.parametrize(
    ("cwd", "manifest_arg"),
    [
        (REPO_ROOT, "gateway/capabilities/backend-rbac-review.yaml"),
        (GATEWAY_ROOT, "capabilities/backend-rbac-review.yaml"),
    ],
)
def test_validate_accepts_documented_paths_from_repo_root_and_gateway_dir(
    cwd: Path,
    manifest_arg: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = cli_module()
    monkeypatch.chdir(cwd)

    exit_code = cli.main(["capabilities", "validate", manifest_arg])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "backend-rbac-review" in captured.out
    assert_no_private_markers(captured.out)
    assert captured.err == ""


def test_validate_invalid_manifest_returns_nonzero_without_body_leak(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = cli_module()
    manifest_path = tmp_path / "broken.yaml"
    manifest_path.write_text(
        f"""
id: broken-capability
name: Broken Capability
version: 0.1.0
visible_description: Broken manifest carrying private debug text.
debug_skill_body: {BODY_ONLY_PHRASE}
input_modes:
  - current_file
internal:
  skill_ref: private-skill
  runner: hermes
  expose_skill_text: false
""".lstrip(),
        encoding="utf-8",
    )

    exit_code = cli.main(["capabilities", "validate", str(manifest_path)])

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err
    assert exit_code != 0
    assert "broken.yaml" in combined_output
    assert_no_private_markers(combined_output)


def test_list_prints_public_capabilities_without_internal_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = cli_module()

    exit_code = cli.main(["capabilities", "list"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "backend-rbac-review" in captured.out
    assert "Backend RBAC Review" in captured.out
    assert_no_private_markers(captured.out)
    assert captured.err == ""


def test_pyproject_declares_skillgw_console_script() -> None:
    pyproject = tomllib.loads((GATEWAY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["skillgw"] == "gateway.app.cli:main"
