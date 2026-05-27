import json
import os
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import smoke_hermes_runner  # noqa: E402
from gateway.app.capabilities.registry import default_registry  # noqa: E402


PRIVATE_TOKENS = (
    "private-token",
    "outside-private-code",
    "internal",
    "skill_text",
    "prompt",
    "raw stdout",
    "raw stderr",
    "SKILL.md",
)


FAKE_HERMES_COMMAND = """
import json
import sys

payload = sys.stdin.read()
if "SKILL.md" in payload or "private-token" in payload:
    sys.exit(7)

json.dump(
    {
        "summary": "Hermes smoke completed.",
        "findings": [],
        "patch": None,
        "recommended_tests": ["python -m pytest"],
        "artifacts": [],
        "safe_rationale": "Public run-result JSON only.",
        "confidence": 0.91,
    },
    sys.stdout,
)
""".strip()


def smoke_capability_with_security(**security_overrides):
    capability = default_registry().find("backend-rbac-review")
    assert capability is not None
    security = capability.security.model_copy(update=security_overrides)
    return capability.model_copy(update={"security": security}, deep=True)


class FakeRegistry:
    def __init__(self, capability):
        self.capability = capability

    def find(self, capability_id: str):
        if capability_id == self.capability.id:
            return self.capability
        return None


def write_sample_workspace(root: Path) -> None:
    root.mkdir()
    (root / "app.py").write_text(
        "def can_read_project(user):\n    return user.is_admin\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample workspace\n\nNon-sensitive smoke fixture.\n",
        encoding="utf-8",
    )
    (root / "SKILL.md").write_text(
        "private-token skill text must never be uploaded\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("private-token=blocked\n", encoding="utf-8")
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")


def symlink_or_skip(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is not available: {exc}")


def assert_no_private_tokens(text: str) -> None:
    lowered = text.lower()
    for token in PRIVATE_TOKENS:
        assert token.lower() not in lowered


def test_smoke_outputs_only_public_run_result_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            FAKE_HERMES_COMMAND,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert set(result) == {
        "summary",
        "findings",
        "patch",
        "recommended_tests",
        "artifacts",
        "safe_rationale",
        "confidence",
    }
    assert result["summary"] == "Hermes smoke completed."
    assert_no_private_tokens(captured.out)


def test_smoke_skips_symlinked_files_outside_sample_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)
    outside_private_file = tmp_path / "outside_private.py"
    outside_private_file.write_text(
        "outside-private-code = 'must not be uploaded'\n",
        encoding="utf-8",
    )
    symlink_or_skip(outside_private_file, sample / "linked_private.py")

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            FAKE_HERMES_COMMAND,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert_no_private_tokens(captured.out)


@pytest.mark.parametrize("skill_filename", ["skill.md", "Skill.md", "SKILL.MD"])
def test_smoke_skips_skill_md_case_variants(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    skill_filename: str,
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)
    (sample / skill_filename).write_text(
        "private-token skill text must never be uploaded\n",
        encoding="utf-8",
    )

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            FAKE_HERMES_COMMAND,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert_no_private_tokens(captured.out)


def test_smoke_respects_explicit_empty_deny_file_globs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "sample-workspace"
    sample.mkdir()
    (sample / "credentials.json").write_text(
        '{"service": "public-smoke-fixture"}\n',
        encoding="utf-8",
    )
    capability = smoke_capability_with_security(
        deny_file_globs=[],
        allow_file_globs=["**/*.json"],
    )
    monkeypatch.setattr(
        smoke_hermes_runner,
        "default_registry",
        lambda: FakeRegistry(capability),
    )
    command = """
import json
import sys

payload = json.loads(sys.stdin.read())
paths = [file["path"] for file in payload["workspace_files"]]
if "credentials.json" not in paths:
    sys.exit(7)
json.dump(
    {
        "summary": "Empty deny list respected.",
        "findings": [],
        "patch": None,
        "recommended_tests": [],
        "artifacts": [],
        "safe_rationale": "Public run-result JSON only.",
        "confidence": 0.9,
    },
    sys.stdout,
)
""".strip()

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            command,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out)["summary"] == "Empty deny list respected."


def test_smoke_rejects_too_many_files_before_running_hermes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "sample-workspace"
    sample.mkdir()
    (sample / "a.py").write_text("print('a')\n", encoding="utf-8")
    (sample / "b.py").write_text("print('b')\n", encoding="utf-8")
    marker = tmp_path / "runner-was-called"
    capability = smoke_capability_with_security(
        max_files=1,
        allow_file_globs=["**/*.py"],
    )
    monkeypatch.setattr(
        smoke_hermes_runner,
        "default_registry",
        lambda: FakeRegistry(capability),
    )
    original_read_small_text_file = smoke_hermes_runner._read_small_text_file

    def fail_if_second_file_is_read(path: Path):
        if path.name == "b.py":
            raise AssertionError("second file should not be read after max_files")
        return original_read_small_text_file(path)

    monkeypatch.setattr(
        smoke_hermes_runner,
        "_read_small_text_file",
        fail_if_second_file_is_read,
    )

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('called')",
            str(marker),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err.strip() == (
        "Sample workspace rejected by input policy: max_files_exceeded"
    )
    assert not marker.exists()


def test_smoke_rejects_total_input_bytes_before_running_hermes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "sample-workspace"
    sample.mkdir()
    (sample / "a.py").write_text("print('too much')\n", encoding="utf-8")
    (sample / "b.py").write_text("print('should not read')\n", encoding="utf-8")
    marker = tmp_path / "runner-was-called"
    capability = smoke_capability_with_security(
        max_total_input_bytes=4,
        allow_file_globs=["**/*.py"],
    )
    monkeypatch.setattr(
        smoke_hermes_runner,
        "default_registry",
        lambda: FakeRegistry(capability),
    )
    original_read_small_text_file = smoke_hermes_runner._read_small_text_file

    def fail_if_second_file_is_read(path: Path):
        if path.name == "b.py":
            raise AssertionError(
                "second file should not be read after max_total_input_bytes"
            )
        return original_read_small_text_file(path)

    monkeypatch.setattr(
        smoke_hermes_runner,
        "_read_small_text_file",
        fail_if_second_file_is_read,
    )

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('called')",
            str(marker),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err.strip() == (
        "Sample workspace rejected by input policy: max_total_input_bytes_exceeded"
    )
    assert not marker.exists()


def test_smoke_command_remainder_passes_option_like_arguments_to_runner(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)
    command = """
import json
import sys

sys.stdin.read()
if "--timeout-seconds" not in sys.argv or "5" not in sys.argv:
    sys.exit(8)
json.dump(
    {
        "summary": "Command remainder preserved.",
        "findings": [],
        "patch": None,
        "recommended_tests": [],
        "artifacts": [],
        "safe_rationale": "Public run-result JSON only.",
        "confidence": 0.9,
    },
    sys.stdout,
)
""".strip()

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            command,
            "--timeout-seconds",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out)["summary"] == "Command remainder preserved."


def test_smoke_unknown_arguments_do_not_echo_secret_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(sample),
            "--unknown-private-token",
            "private-token",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err.strip() == "Invalid smoke script arguments."
    assert_no_private_tokens(captured.err)


def test_smoke_unknown_capability_fails_without_private_leakage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "sample-workspace"
    write_sample_workspace(sample)

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "missing-capability",
            "--sample",
            str(sample),
            "--command",
            sys.executable,
            "-c",
            FAKE_HERMES_COMMAND,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "Capability not found." in captured.err
    assert_no_private_tokens(captured.err)


def test_smoke_missing_sample_path_fails_without_private_leakage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_sample = tmp_path / "does-not-exist"

    exit_code = smoke_hermes_runner.main(
        [
            "--capability",
            "backend-rbac-review",
            "--sample",
            str(missing_sample),
            "--command",
            sys.executable,
            "-c",
            FAKE_HERMES_COMMAND,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "Sample workspace does not exist." in captured.err
    assert_no_private_tokens(captured.err)
