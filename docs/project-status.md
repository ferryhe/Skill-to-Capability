# Project Status

## Current State

Repository bootstrap and full roadmap are complete. Contract validation work is now in progress on a dedicated branch.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone A: Contract Freeze**

The current task is **PR A1: Schema and fixture validation**.

## Completed

- Bootstrap README and docs.
- Added architecture/security/capability/API/VSCode/MCP docs.
- Added initial JSON schemas.
- Added example `backend-rbac-review` capability manifest.
- Added full development roadmap.
- Merged PR #1: full development roadmap and project status tracker.

## Current Branch

`feat/contract-fixtures-validator`

## Current PR Scope

**PR A1: Schema and fixture validation**

- Add valid/invalid contract fixtures under `tests/contracts/fixtures/`.
- Add `scripts/validate-contracts.py`.
- Validate JSON schemas, fixtures, and example capability manifests.
- Keep private skill leakage checks executable through invalid fixtures.

## Next PRs

1. **PR A2: Contract docs alignment**
   - Ensure docs and schemas use identical field names.
   - Make every JSON example parseable.

2. **PR B1: Gateway skeleton**
   - Add FastAPI app, `/health`, and pytest setup.

3. **PR B2: Capability manifest registry**
   - Add manifest model, YAML loader, public view stripping, and `/v1/capabilities` endpoints.

## Verification Baseline

Current docs/schema baseline:

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
