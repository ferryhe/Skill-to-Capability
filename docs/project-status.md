# Project Status

## Current State

Repository bootstrap, roadmap definition, Contract Freeze baseline, contract doc alignment, the Gateway skeleton/health baseline, the Gateway capability registry, Gateway input policy utilities, the Gateway mock run endpoint, Gateway output redaction/error filtering, the C1 SKILL.md parser/converter, the C2 `skillgw` CLI, the D1 Hermes runner contract, the D2 task store/async status API, the D3 real Hermes smoke script, the E1 VSCode extension skeleton/settings/auth placeholder, the E2 VSCode capability list UI, the E3 VSCode workspace context collector, the E4 VSCode run capability/report panel flow, the E5 VSCode patch preview/apply flow, the E6 VSCode recommended tests execution flow, the F1 MCP server skeleton, the F2 MCP list/run/status/result/cancel tools, the F3 Hermes/Cline smoke docs, the G1 Gateway token auth plus tenant identity baseline, the G2 capability policy baseline, the G3 internal audit log baseline, and the G4 security regression suite are complete on their implementation branches.

## Source of Truth

- Repository: `ferryhe/Skill-to-Capability`
- Default branch: `main`
- Development branch policy: branch from latest `origin/main`, one narrow PR at a time.

## Active Milestone

**Milestone H: End-to-end Closure and Release Prep**

Gateway MVP work is complete through B5 with the minimal FastAPI service skeleton, health-check validation, capability registry endpoints, input policy validation, mock runner flow, output filtering, sensitive-value redaction, and unified public error responses in place. Milestone C is complete with C1 parser/converter support plus the C2 `skillgw` CLI for generating, validating, and listing capability manifests without exposing skill body text or internal manifest fields on stdout. Milestone D is complete with the D1 mockable Hermes runner contract, D2 task store/status lifecycle, and D3 real Hermes smoke script. Milestone E is complete with the VSCode extension package skeleton, settings contributions, SecretStorage token placeholder, public-only Gateway client, command palette capability refresh, Explorer tree view, public-field-only capability detail output, bounded workspace context collection for current file, selection, selected files, and git diff flows, Gateway run command wiring, a public-only report webview, remembered public patch output, diff preview, user confirmation, VSCode WorkspaceEdit patch application with workspace path policy checks, and user-confirmed recommended test execution in a workspace-scoped VSCode terminal. Milestone F has the F1 MCP adapter bootstrap, F2 tool surface, and F3 smoke docs in place on implementation branches with a TypeScript package, stdio server construction, Gateway client, env/CLI config handling, five registered public MCP tools, public-field stripping, token/error redaction tests, and safe Hermes/Cline/Roo-compatible MCP configuration examples. Milestone G has G1 Gateway API token authentication, G2 server-only capability policy with tenant visibility filtering and role-based run permissions, G3 internal audit logging with sanitized task lifecycle/input/output/approval metadata, and G4 security regression coverage for prompt injection, internal leakage, path traversal, secret upload, and error redaction.

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
- Added PR D3 real Hermes smoke script with a non-sensitive sample workspace, public-only run-result stdout, local command override for tests/debugging, and development docs warning against committing private skills or raw runner output.
- Added PR E1 VSCode extension skeleton with command activation, Gateway settings, SecretStorage token placeholder, and a minimal public-only Gateway client for listing/getting capabilities.
- Added PR E2 VSCode capability list UI with command palette refresh, Explorer tree provider for Gateway public capabilities, OutputChannel detail display, and UI-side public-field filtering for server-only fields.
- Added PR E3 VSCode workspace context collector with public run-request payload construction, current file/selection/selected file/git diff sources, client-side denylist enforcement, workspace escape rejection, and configured file count/byte limits.
- Added PR E4 VSCode run capability flow with Gateway `POST /v1/capabilities/{id}/run` client support, current file/git diff/no-context command modes, instruction prompt, queued/completed task metadata handling, and an escaped report panel for summary/findings/safe rationale/confidence/recommended tests/artifact metadata that ignores server-only fields.
- Added PR E5 VSCode patch preview/apply with completed-report `result.patch` memory, diff preview, modal user confirmation, unified diff hunk validation, denylisted/path traversal rejection, and VSCode WorkspaceEdit full-document replacements scoped to the remembered workspace folder.
- Added PR E6 VSCode recommended tests execution with completed-report `result.recommended_tests` memory, trimmed command selection, workspace re-resolution, multi-root workspace picking, modal user confirmation, and ordered command execution in a VSCode terminal rooted at the selected workspace.
- Added PR F1 MCP adapter bootstrap with a TypeScript package, MCP stdio server skeleton, env/CLI Gateway URL/token config parsing, public-only Gateway client list call, redacted Gateway/client errors, and tests that keep the five MCP tools reserved for F2.
- Added PR F2 MCP adapter tools on branch `codex/pr-f2-mcp-tools` with `list_capabilities`, `run_capability`, `get_task_status`, `get_task_result`, and `cancel_task`, routed through the Gateway client with nested `request` forwarding for runs, recursive public-only response filtering, safe tool descriptions, and sanitized MCP tool error results.
- Added PR F3 Hermes/Cline smoke docs on branch `codex/pr-f3-mcp-smoke-docs` with local Gateway + MCP adapter smoke steps, five-tool discovery checks, non-sensitive sample workspace run guidance, safe Hermes failure expectations, and placeholder-only Hermes plus Cline/Roo-compatible MCP config examples.
- Added PR G1 token auth and tenant identity on branch `codex/pr-g1-token-auth-tenant` with protected capability/task endpoints, `Authorization: Bearer` token validation from `SKILL_GATEWAY_API_TOKENS`, fail-closed missing-config behavior, explicit `SKILL_GATEWAY_AUTH_MODE=dev` / `SKILL_GATEWAY_AUTH_DISABLED=true` local bypass, request identity tenant parsing, and sanitized 401 errors.
- Added PR G2 capability policy on branch `codex/pr-g2-capability-policy` with server-only `internal.policy`, tenant allowlist visibility filtering for list/get/run, token-bound tenant/role identity from fail-closed `SKILL_GATEWAY_API_TOKEN_IDENTITIES`, legacy token defaults that do not trust tenant/role headers, task owner enforcement for status/result/cancel, explicit developer-only policy for the bundled patch-capable capability, sanitized 404/403 behavior, and tests proving tenant A cannot see tenant B capability while viewer/developer run permissions differ.
- Added PR G3 internal audit log on branch `codex/pr-g3-audit-log` with in-memory audit models/store, sanitized task lifecycle events for queued/running/completed/failed/cancelled transitions, safe input/output metadata, safe actor metadata, approval event support, and tests proving audit can query task lifecycle without storing skill body, full prompt, raw tokens, raw runner output, or secrets.
- Added PR G4 security regression suite on branch `codex/pr-g4-security-regression-suite` with Gateway tests for prompt injection, internal leakage, path traversal, secret upload, and error redaction, plus stricter output filtering for full prompt and raw runner output text.

## Milestone Baseline

- Valid/invalid contract fixtures live under `tests/contracts/fixtures/`.
- `scripts/validate-contracts.py` validates schemas, fixtures, and example capability manifests.
- Private skill leakage checks remain covered through invalid fixtures.

## Next PRs

1. **PR H1: Local dev compose / scripts**
   - Add local dev compose/scripts to run Gateway, VSCode, and MCP flows together.

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

Gateway D3 validation:

```bash
cd gateway
python -m pytest tests/test_hermes_smoke_script.py -q
python -m pytest tests/test_hermes_runner_contract.py tests/test_tasks_api.py tests/test_task_store.py -q
python -m pytest tests/ -q
# Requires local Hermes CLI/config.
python scripts/smoke_hermes_runner.py --capability backend-rbac-review --sample ../examples/sample-workspace
python ../scripts/validate-contracts.py
git diff --check
```

Gateway G4 validation:

```bash
cd gateway
python -m pytest tests/security -q
python -m pytest tests/test_output_filter.py tests/test_error_redaction.py tests/test_run_capability.py tests/test_input_policy.py tests/test_audit_log.py tests/test_hermes_runner_contract.py -q
python -m pytest tests/ -q
git diff --check
```

VSCode E1 validation:

```bash
cd vscode-extension
npm install
npm run compile
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

VSCode E2 validation:

```bash
cd vscode-extension
npm run compile
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

VSCode E3 validation:

```bash
cd vscode-extension
npm run test:workspaceCollector
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

VSCode E4 validation:

```bash
cd vscode-extension
npm run test:runCapability
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

VSCode E5 validation:

```bash
cd vscode-extension
npm run test:applyPatch
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

VSCode E6 validation:

```bash
cd vscode-extension
npm run test:recommendedTests
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

MCP Adapter F1 validation:

```bash
cd mcp-adapter
npm install
npm run build
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

MCP Adapter F2 validation:

```bash
cd mcp-adapter
npm run build
npm test
cd ..
python scripts/validate-contracts.py
git diff --check
```

MCP Adapter F3 validation:

```bash
python scripts/validate-contracts.py
python -m json.tool examples/mcp/cline-config.json
python -c "import yaml; yaml.safe_load(open('examples/mcp/hermes-config.yaml', encoding='utf-8'))"
git diff --check
```

## Known Risks

- Real Hermes smoke script exists, but actual execution requires a local Hermes CLI and developer-specific Hermes configuration; because `backend-rbac-review` now defaults to the Hermes runner, Gateway synchronous `/v1/capabilities/backend-rbac-review/run` calls also return a safe 502 when Hermes is unavailable.
- Async queued tasks do not have a background worker yet; D2 only records queued lifecycle state and exposes status/cancel/result APIs.
- VSCode Extension currently has the E1 skeleton/settings/auth/client baseline, E2 capability list UI, E3 workspace context collector, E4 Gateway run/report panel flow, E5 patch preview/apply flow, and E6 user-confirmed recommended tests execution.
- E5 applies only existing-file unified diff hunks after preview and confirmation; file create/delete/rename support remains intentionally out of scope.
- MCP Adapter F3 adds real client smoke documentation and safe config templates; actual Hermes execution still depends on developer-specific local Hermes and Gateway runner setup.
- No CI exists yet; validation is currently local only.
- Example skill is intentionally non-sensitive placeholder text.
