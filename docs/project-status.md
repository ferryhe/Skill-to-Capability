# Project Status

## Current State

Repository bootstrap, roadmap definition, Contract Freeze baseline, contract doc alignment, the Gateway skeleton/health baseline, the Gateway capability registry, and Gateway input policy utilities are complete.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone B: Gateway MVP**

Gateway MVP work is underway with the minimal FastAPI service skeleton, health-check validation, capability registry endpoints, and input policy validation complete.

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

## Milestone Baseline

- Valid/invalid contract fixtures live under `tests/contracts/fixtures/`.
- `scripts/validate-contracts.py` validates schemas, fixtures, and example capability manifests.
- Private skill leakage checks remain covered through invalid fixtures.

## Next PRs

1. **PR B4: Mock runner and run endpoint**
   - Add runner interface, mock runner, and `POST /v1/capabilities/{id}/run`.

2. **PR B5: Output filter and redaction**
   - Add output redaction, skill/internal prompt leakage filtering, and unified redacted error responses.

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

## Known Risks

- Real Hermes runner integration is not implemented yet.
- VSCode Extension and MCP Adapter are not bootstrapped yet.
- No CI exists yet; validation is currently local only.
- Example skill is intentionally non-sensitive placeholder text.
