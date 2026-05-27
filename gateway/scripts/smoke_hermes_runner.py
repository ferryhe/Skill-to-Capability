import argparse
import hashlib
import json
import sys
from pathlib import Path

GATEWAY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.app.capabilities.manifest import CapabilityManifest, SecurityPolicy
from gateway.app.capabilities.registry import default_registry
from gateway.app.runners.hermes_runner import HermesCapabilityRunner
from gateway.app.runners.json_output import HermesRunnerError
from gateway.app.security.errors import InputPolicyViolation
from gateway.app.security.input_policy import (
    DEFAULT_DENY_FILE_GLOBS,
    InputPolicy,
    WorkspaceInputFile,
    validate_workspace_context_files,
)
from gateway.app.tasks.models import CapabilityRunRequest


DEFAULT_INSTRUCTION = (
    "Run a non-sensitive smoke review against this sample workspace and return "
    "only the public run-result JSON shape."
)
ALLOWED_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".json",
    ".yaml",
    ".yml",
}
RESERVED_FILE_NAMES = {"SKILL.md"}
MAX_SAMPLE_FILE_BYTES = 64_000


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SafeArgumentError:
        return _fail("Invalid smoke script arguments.")
    if args.command is not None and not args.command:
        return _fail("Invalid smoke script arguments.")

    capability = default_registry().find(args.capability)
    if capability is None:
        return _fail("Capability not found.")
    if capability.internal.runner != "hermes":
        return _fail("Capability is not configured for the Hermes runner.")

    sample_path = Path(args.sample)
    if not sample_path.exists() or not sample_path.is_dir():
        return _fail("Sample workspace does not exist.")

    try:
        workspace_files = _collect_workspace_files(sample_path, capability)
    except SmokeInputError as exc:
        return _fail(str(exc))

    request = CapabilityRunRequest(
        workspace={
            "name": sample_path.name,
            "root_uri": sample_path.resolve().as_uri(),
            "files": [
                {
                    "path": file.path,
                    "content": file.content,
                    "sha256": file.sha256,
                }
                for file in workspace_files
            ],
        },
        instruction=args.instruction,
        client={"type": "cli", "version": "0.1.0"},
    )
    command = tuple(args.command) if args.command is not None else (
        args.hermes_bin,
        "run",
        "--skill",
        capability.internal.skill_ref,
        "--json",
    )
    runner = HermesCapabilityRunner(
        command=command,
        timeout_seconds=args.timeout_seconds,
    )

    try:
        result = runner.run(capability, request, workspace_files)
    except HermesRunnerError as exc:
        return _fail(str(exc))

    print(json.dumps(result.model_dump(mode="json"), separators=(",", ":")))
    return 0


class SmokeInputError(ValueError):
    """Safe public error for smoke workspace collection failures."""


def _build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        description="Run a non-sensitive Hermes runner smoke test.",
    )
    parser.add_argument("--capability", required=True)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--hermes-bin", default="hermes")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        help="Full runner command override for tests or local debugging.",
    )
    return parser


class SafeArgumentError(ValueError):
    """Raised when CLI parsing fails without exposing raw arguments."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SafeArgumentError("Invalid smoke script arguments.")


def _collect_workspace_files(
    sample_path: Path,
    capability: CapabilityManifest,
) -> list[WorkspaceInputFile]:
    policy = _input_policy_from_security(capability.security)
    files: list[WorkspaceInputFile] = []
    total_input_bytes = 0
    for path in sorted(sample_path.rglob("*")):
        if not path.is_file() or _should_skip_path(sample_path, path):
            continue
        if policy.max_files is not None and len(files) >= policy.max_files:
            raise SmokeInputError(
                "Sample workspace rejected by input policy: max_files_exceeded"
            )
        content = _read_small_text_file(path)
        if content is None:
            continue
        total_input_bytes += len(content.encode("utf-8"))
        if (
            policy.max_total_input_bytes is not None
            and total_input_bytes > policy.max_total_input_bytes
        ):
            raise SmokeInputError(
                "Sample workspace rejected by input policy: "
                "max_total_input_bytes_exceeded"
            )
        relative_path = path.relative_to(sample_path).as_posix()
        files.append(
            WorkspaceInputFile(
                path=relative_path,
                content=content,
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )

    try:
        return validate_workspace_context_files(files, policy)
    except InputPolicyViolation as exc:
        raise SmokeInputError(
            f"Sample workspace rejected by input policy: {exc.code}"
        ) from None


def _should_skip_path(sample_path: Path, path: Path) -> bool:
    relative_path = path.relative_to(sample_path)
    if path.is_symlink():
        return True
    if _contains_symlink_parent(sample_path, relative_path):
        return True
    relative_parts = relative_path.parts
    if any(part.startswith(".") for part in relative_parts):
        return True
    if path.name.lower() in {name.lower() for name in RESERVED_FILE_NAMES}:
        return True
    if path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES:
        return True
    return path.stat().st_size > MAX_SAMPLE_FILE_BYTES


def _contains_symlink_parent(sample_path: Path, relative_path: Path) -> bool:
    current = sample_path
    for part in relative_path.parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _read_small_text_file(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SmokeInputError("Sample workspace could not be read.") from exc
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _input_policy_from_security(security: SecurityPolicy | None) -> InputPolicy:
    if security is None:
        return InputPolicy()
    return InputPolicy(
        max_files=security.max_files,
        max_total_input_bytes=security.max_total_input_bytes,
        deny_file_globs=(
            security.deny_file_globs
            if security.deny_file_globs is not None
            else list(DEFAULT_DENY_FILE_GLOBS)
        ),
        allow_file_globs=security.allow_file_globs,
    )


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
