# Project Status

## Current State

Repository bootstrap, roadmap definition, Contract Freeze baseline, contract doc alignment, the Gateway skeleton/health baseline, the Gateway capability registry, Gateway input policy utilities, the Gateway mock run endpoint, Gateway output redaction/error filtering, and the C1 SKILL.md parser/converter are complete.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone C: Skill-to-Capability Converter**

Gateway MVP work is complete through B5 with the minimal FastAPI service skeleton, health-check validation, capability registry endpoints, input policy validation, mock runner flow, output filtering, sensitive-value redaction, and unified public error responses in place. Milestone C is underway with C1 parser/converter support for generating safe draft capability manifests from SKILL.md frontmatter without copying skill body text.

## Completed

- Bootstrap README and docs.
- Added architecture/security/capability/API/VSCode/MCP docs.
- Added initial JSON schemas.
- Added example `backend-rbac-review` capability manifest.
- Added full development roadmap.
- Merged PR #1: full development roadmap and project status tracker.
- Added contract fixtures and `scripts/validate-contracts.py` for local validation.
- Aligned API, VSCode, and MCP contract docs with current schemas and fixtures.
- Added PR B1 FastAPI Gateway skeleton with `/health` endpoint and pytest health test.
- Added PR B2 capability manifest registry with YAML loading, public view stripping, and `/v1/capabilities` endpoints.
- Added PR B3 input policy utilities with workspace-relative path validation, deny globs, byte limits, and fail-closed secret-like content rejection.
- Added PR B4 mock runner flow with `POST /v1/capabilities/{id}/run`, synchronous completed task results, and manifest-backed workspace file policy enforcement.
- Added PR B5 output filtering and redaction with Bearer/API-key/secret/path scrubbing, internal prompt/skill leakage blocking, and unified redacted `error` responses.
- Added PR C1 SKILL.md frontmatter parser and converter that emits `CapabilityManifest` draft objects with `internal.skill_ref`, `internal.expose_skill_text = false`, and no skill body text in serialized output.

## Milestone Baseline

- Valid/invalid contract fixtures live under `tests/contracts/fixtures/`.
- `scripts/validate-contracts.py` validates schemas, fixtures, and example capability manifests.
- Private skill leakage checks remain covered through invalid fixtures.

## Next PRs

1. **PR C2: skillgw CLI**
   - Add CLI commands to generate, validate, and list capability manifests using the C1 converter.
   - Ensure generated CLI output preserves the C1/B5 no-skill-body and no-private-internal-data guarantees.
   - Preserve the B5 handoff rule: all future runner/task result paths must pass through the output filter, and all public failures must use the redacted `error` envelope.

## Verification Baseline

Available docs/schema baseline:

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate-contracts.py
python3 -m json.tool schemas/capability.schema.json >/dev/null
python3 -m json.tool schemas/run-request.schema.json >/dev/null
python3 -m json.tool schemas/run-result.schema.json >/dev/null
git diff --check
```

Gateway B1 validation:

```bash
cd gateway
python -m pip install -e .[dev]
python -m pytest tests/ -q
```

Gateway B2 validation:

```bash
cd gateway
python -m pytest tests/test_capability_registry.py tests/test_capability_api.py -q
python -m pytest tests/ -q
```

Gateway B3 validation:

```bash
cd gateway
python -m pytest tests/test_input_policy.py -q
python -m pytest tests/ -q
```

Gateway B4 validation:

```bash
cd gateway
python -m pytest tests/test_run_capability.py -q
python -m pytest tests/ -q
```

Gateway B5 validation:

```bash
cd gateway
python -m pytest tests/test_output_filter.py tests/test_error_redaction.py -q
python -m pytest tests/test_run_capability.py -q
python -m pytest tests/ -q
python ../scripts/validate-contracts.py
git diff --check
```

Gateway C1 validation:

```bash
cd gateway
python -m pytest tests/test_skill_converter.py -q
python -m pytest tests/ -q
python ../scripts/validate-contracts.py
git diff --check
```

## Known Risks

- Real Hermes runner integration is not implemented yet.
- `skillgw` CLI is not implemented yet.
- VSCode Extension and MCP Adapter are not bootstrapped yet.
- No CI exists yet; validation is currently local only.
- Example skill is intentionally non-sensitive placeholder text.
