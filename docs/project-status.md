# Project Status

## Current State

Repository bootstrap is complete. The project currently contains architecture, security model, API/VSCode/MCP contracts, JSON schemas, an example capability manifest, and a placeholder example skill.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone A: Contract Freeze**

The next implementation work should turn the written contracts into executable validation fixtures and schema checks.

## Completed

- Bootstrap README and docs.
- Added architecture/security/capability/API/VSCode/MCP docs.
- Added initial JSON schemas.
- Added example `backend-rbac-review` capability manifest.
- Added full development roadmap.

## Next PRs

1. **PR A1: Schema and fixture validation**
   - Add `tests/contracts/fixtures/*`.
   - Add `scripts/validate-contracts.py`.
   - Verify valid/invalid capability and run-result examples.

2. **PR A2: Contract docs alignment**
   - Ensure docs and schemas use identical field names.
   - Make every JSON example parseable.

3. **PR B1: Gateway skeleton**
   - Add FastAPI app, `/health`, and pytest setup.

## Verification Baseline

Current docs/schema baseline:

```bash
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
