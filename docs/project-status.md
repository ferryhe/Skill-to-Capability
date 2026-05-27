# Project Status

## Current State

Repository bootstrap, roadmap definition, Contract Freeze baseline, contract doc alignment, the Gateway skeleton/health baseline, the Gateway capability registry, Gateway input policy utilities, the Gateway mock run endpoint, Gateway output redaction/error filtering, the C1 SKILL.md parser/converter, the C2 `skillgw` CLI, the D1 Hermes runner contract, and the D2 task store/async status API are complete.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone D: Real Runner and Task Lifecycle**

Gateway MVP work is complete through B5 with the minimal FastAPI service skeleton, health-check validation, capability registry endpoints, input policy validation, mock runner flow, output filtering, sensitive-value redaction, and unified public error responses in place. Milestone C is complete with C1 parser/converter support plus the C2 `skillgw` CLI for generating, validating, and listing capability manifests without exposing skill body text or internal manifest fields on stdout. Milestone D is in progress with the D1 mockable Hermes runner contract and D2 task store/status lifecycle complete; D3 real Hermes smoke is next.

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
- Added PR C2 `skillgw` CLI with `capabilities generate`, `capabilities validate`, and `capabilities list`, including public stdout guarantees and invalid-manifest nonzero exits.
- Added PR D1 Hermes runner contract with mockable subprocess execution, strict JSON result parsing, schema validation, output filtering, and sanitized runner failures.
- Added PR D2 task store and async status API with in-memory lifecycle states, task status/result/cancel endpoints, queued async run responses, completed result lookup, and redacted failed-task error envelopes.

## Milestone Baseline

- Valid/invalid contract fixtures live under `tests/contracts/fixtures/`.
- `scripts/validate-contracts.py` validates schemas, fixtures, and example capability manifests.
- Private skill leakage checks remain covered through invalid fixtures.

## Next PRs

1. **PR D3: Real Hermes smoke**
   - Add a local smoke script for non-sensitive Hermes runner execution.
   - Document how to run the smoke without committing private skills or raw runner output.
   - Preserve the B5/D1/D2 handoff rule: all runner outputs and task result/failure paths must use filtered public result shapes and redacted `error` envelopes.

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

Gateway C2 validation:

```bash
cd gateway
python -m pytest tests/test_cli.py -q
python -m pytest tests/ -q
python ../scripts/validate-contracts.py
git diff --check
```

Gateway D1 validation:

```bash
cd gateway
python -m pytest tests/test_hermes_runner_contract.py -q
python -m pytest tests/test_run_capability.py tests/test_output_filter.py -q
python -m pytest tests/ -q
python ../scripts/validate-contracts.py
git diff --check
```

Gateway D2 validation:

```bash
cd gateway
python -m pytest tests/test_tasks_api.py -q
python -m pytest tests/test_run_capability.py tests/test_output_filter.py tests/test_error_redaction.py tests/test_hermes_runner_contract.py -q
python ../scripts/validate-contracts.py
git diff --check
```

## Known Risks

- Real Hermes smoke execution is not implemented yet; D1 only defines the mockable subprocess contract.
- Async queued tasks do not have a background worker yet; D2 only records queued lifecycle state and exposes status/cancel/result APIs.
- VSCode Extension and MCP Adapter are not bootstrapped yet.
- No CI exists yet; validation is currently local only.
- Example skill is intentionally non-sensitive placeholder text.
