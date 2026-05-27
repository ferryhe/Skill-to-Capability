# Project Status

## Current State

Repository bootstrap, roadmap definition, Contract Freeze baseline, and contract doc alignment are complete.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone A: Contract Freeze**

This milestone now has a usable baseline for schema, fixture, and manifest validation.

## Completed

- Bootstrap README and docs.
- Added architecture/security/capability/API/VSCode/MCP docs.
- Added initial JSON schemas.
- Added example `backend-rbac-review` capability manifest.
- Added full development roadmap.
- Merged PR #1: full development roadmap and project status tracker.
- Added contract fixtures and `scripts/validate-contracts.py` for local validation.
- Aligned API, VSCode, and MCP contract docs with current schemas and fixtures.

## Milestone Baseline

- Valid/invalid contract fixtures live under `tests/contracts/fixtures/`.
- `scripts/validate-contracts.py` validates schemas, fixtures, and example capability manifests.
- Private skill leakage checks remain covered through invalid fixtures.

## Next PRs

1. **PR B1: Gateway skeleton**
   - Add FastAPI app, `/health`, and pytest setup.

2. **PR B2: Capability manifest registry**
   - Add manifest model, YAML loader, public view stripping, and `/v1/capabilities` endpoints.

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

## Known Risks

- Real Hermes runner integration is not implemented yet.
- VSCode Extension and MCP Adapter are not bootstrapped yet.
- No CI exists yet; validation is currently local only.
- Example skill is intentionally non-sensitive placeholder text.
