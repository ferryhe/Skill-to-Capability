# Skill-to-Capability Platform Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a platform that wraps private AI skills as secure server-side capabilities, usable through a Skill Gateway API, VSCode Extension, and MCP Adapter without exposing skill text or private prompts.

**Architecture:** Private skills stay in the Gateway runtime. Public clients only receive capability metadata and structured results. VSCode handles workspace context collection and patch application; MCP exposes the same Gateway capabilities to external agents.

**Tech Stack:** Python + FastAPI + Pydantic for Gateway; TypeScript + VSCode API for extension; TypeScript MCP SDK for adapter; JSON Schema for cross-component contracts.

---

## Phase 0: Contract and Threat Model

### Task 0.1: Define public/private manifest boundary

**Objective:** Establish what can be sent to clients and what must remain server-side.

**Files:**
- Create/modify: `docs/security-model.md`
- Create/modify: `docs/capability-authoring.md`
- Create: `schemas/capability.schema.json`

**Steps:**
1. Write JSON Schema with `internal` section explicitly marked server-only.
2. Document client-facing allowlist.
3. Add examples of forbidden fields.
4. Verify schema parses with `python -m json.tool schemas/capability.schema.json`.

**Acceptance Criteria:**
- `internal` is documented as Gateway-only.
- Public client responses have an explicit allowlist.
- Security doc includes prompt-injection and path traversal cases.

### Task 0.2: Define request/result schemas

**Objective:** Freeze the API payloads shared by Gateway, VSCode, and MCP.

**Files:**
- Create: `schemas/run-request.schema.json`
- Create: `schemas/run-result.schema.json`
- Modify: `docs/api-contract.md`

**Steps:**
1. Define workspace context, instruction, options, and client metadata.
2. Define result with summary, findings, patch, recommended_tests, artifacts, safe_rationale.
3. Validate schemas with `python -m json.tool`.

**Acceptance Criteria:**
- Result schema contains no prompt/trace/skill fields.
- Request schema supports files, diff, selection, and client metadata.

---

## Phase 1: Skill Gateway MVP

### Task 1.1: Bootstrap FastAPI project

**Objective:** Create a minimal Gateway service with health endpoint.

**Files:**
- Create: `gateway/pyproject.toml`
- Create: `gateway/app/main.py`
- Create: `gateway/app/api/health.py`
- Create: `gateway/tests/test_health.py`

**Steps:**
1. Add FastAPI/Pydantic/pytest dependencies.
2. Implement `/health`.
3. Add pytest using FastAPI TestClient.
4. Run `pytest gateway/tests -q`.

**Acceptance Criteria:**
- Health test passes.
- App import path is documented.

### Task 1.2: Implement manifest loader and public view

**Objective:** Load capability YAML files and strip server-only fields.

**Files:**
- Create: `gateway/app/capabilities/manifest.py`
- Create: `gateway/app/capabilities/registry.py`
- Create: `gateway/tests/test_capability_registry.py`
- Create: `gateway/capabilities/backend-rbac-review.yaml`

**Steps:**
1. Define Pydantic models for manifest.
2. Load YAML manifests from configured directory.
3. Implement `to_public_dict()` that removes `internal`.
4. Test that public dict never includes internal keys.

**Acceptance Criteria:**
- Public list/detail cannot leak `internal`.
- Invalid manifests fail validation.

### Task 1.3: Add capability API endpoints

**Objective:** Expose public capability list/detail.

**Files:**
- Create: `gateway/app/api/capabilities.py`
- Modify: `gateway/app/main.py`
- Create: `gateway/tests/test_capability_api.py`

**Steps:**
1. Implement `GET /v1/capabilities`.
2. Implement `GET /v1/capabilities/{id}`.
3. Add tests for normal and not-found paths.
4. Add regression test asserting response text does not contain `skill_ref` or `model_policy`.

**Acceptance Criteria:**
- Capability endpoints return public fields only.

### Task 1.4: Add mock runner and run endpoint

**Objective:** Prove end-to-end request/result flow without real LLM.

**Files:**
- Create: `gateway/app/runners/base.py`
- Create: `gateway/app/runners/mock_runner.py`
- Create: `gateway/app/tasks/models.py`
- Modify: `gateway/app/api/capabilities.py`
- Create: `gateway/tests/test_run_capability.py`

**Steps:**
1. Define runner interface.
2. Implement mock runner returning summary/findings/patch/recommended_tests.
3. Implement `POST /v1/capabilities/{id}/run`.
4. Validate input and output.
5. Add tests for successful run and denied file upload.

**Acceptance Criteria:**
- `/run` returns valid result.
- `.env` upload is denied.
- Result does not contain prompt/skill/internal fields.

---

## Phase 2: Skill-to-Capability Conversion

### Task 2.1: Parse SKILL.md frontmatter

**Objective:** Extract public metadata and internal runner references from skill files.

**Files:**
- Create: `gateway/app/skills/converter.py`
- Create: `gateway/tests/test_skill_converter.py`
- Create: `examples/skills/backend-rbac-review/SKILL.md`

**Steps:**
1. Parse YAML frontmatter.
2. Map `name` and `description` into manifest draft.
3. Preserve skill body only as private source, never in public manifest.
4. Test generated manifest has `internal.expose_skill_text = false`.

**Acceptance Criteria:**
- Converter output validates against manifest model.
- Converter output does not include skill body.

### Task 2.2: Add CLI commands for manifest generation and validation

**Objective:** Let maintainers generate and validate capability manifests.

**Files:**
- Create: `gateway/app/cli.py`
- Modify: `gateway/pyproject.toml`
- Create: `gateway/tests/test_cli.py`

**Commands:**
```bash
skillgw capabilities generate --skill examples/skills/backend-rbac-review/SKILL.md --out /tmp/backend-rbac-review.yaml
skillgw capabilities validate gateway/capabilities/backend-rbac-review.yaml
skillgw capabilities list
```

**Acceptance Criteria:**
- Commands exit 0 for valid input.
- Generated manifest excludes skill body.

---

## Phase 3: Hermes Runner MVP

### Task 3.1: Implement server-side Hermes subprocess runner

**Objective:** Run a private skill through Hermes from the Gateway process boundary.

**Files:**
- Create: `gateway/app/runners/hermes_runner.py`
- Create: `gateway/tests/test_hermes_runner_contract.py`

**Steps:**
1. Build a prompt requiring strict JSON output.
2. Invoke Hermes subprocess with private skill loaded server-side.
3. Parse/validate JSON result.
4. Add mockable subprocess tests.

**Acceptance Criteria:**
- Runner never returns raw prompt or skill.
- Invalid JSON fails safely or retries.

### Task 3.2: Add output redaction and filtering

**Objective:** Strip sensitive data from runner output and errors.

**Files:**
- Create: `gateway/app/security/redaction.py`
- Create: `gateway/app/security/output_filter.py`
- Create: `gateway/tests/test_output_filter.py`

**Acceptance Criteria:**
- API keys, bearer tokens, internal paths, and known private skill markers are redacted.
- Prompt injection asking for skill text returns safe refusal or filtered response.

---

## Phase 4: VSCode Extension MVP

### Task 4.1: Bootstrap extension

**Objective:** Create a VSCode extension skeleton with Gateway settings.

**Files:**
- Create: `vscode-extension/package.json`
- Create: `vscode-extension/tsconfig.json`
- Create: `vscode-extension/src/extension.ts`
- Create: `vscode-extension/src/api/client.ts`

**Acceptance Criteria:**
- Extension activates.
- Gateway URL setting is available.
- `refreshCapabilities` command calls Gateway.

### Task 4.2: Implement workspace context collector

**Objective:** Collect current file, selected files, selection, and git diff safely.

**Files:**
- Create: `vscode-extension/src/context/workspaceCollector.ts`
- Create: `vscode-extension/src/context/policy.ts`
- Create: `vscode-extension/src/test/workspaceCollector.test.ts`

**Acceptance Criteria:**
- Denylisted files are skipped.
- Byte limits enforced.
- Git diff collection works or fails gracefully.

### Task 4.3: Run capability and render report

**Objective:** Let a user run a capability from command palette and see results.

**Files:**
- Create: `vscode-extension/src/commands/runCapability.ts`
- Create: `vscode-extension/src/webview/reportPanel.ts`

**Acceptance Criteria:**
- User can select a capability.
- Result summary/findings render in VSCode.
- Internal fields are ignored if present.

### Task 4.4: Preview and apply patch

**Objective:** Apply Gateway-returned changes to workspace after user confirmation.

**Files:**
- Create: `vscode-extension/src/patch/diffPreview.ts`
- Create: `vscode-extension/src/patch/applyPatch.ts`
- Create: `vscode-extension/src/test/applyPatch.test.ts`

**Acceptance Criteria:**
- Patch paths are workspace-contained.
- User sees diff preview before apply.
- Apply modifies files through VSCode APIs.

---

## Phase 5: MCP Adapter MVP

### Task 5.1: Bootstrap MCP server

**Objective:** Create a stdio MCP server that can call Gateway.

**Files:**
- Create: `mcp-adapter/package.json`
- Create: `mcp-adapter/tsconfig.json`
- Create: `mcp-adapter/src/server.ts`
- Create: `mcp-adapter/src/gatewayClient.ts`

**Acceptance Criteria:**
- MCP server starts over stdio.
- Gateway URL/token config works.

### Task 5.2: Implement MCP tools

**Objective:** Expose the stable tool surface.

**Files:**
- Create: `mcp-adapter/src/tools/listCapabilities.ts`
- Create: `mcp-adapter/src/tools/runCapability.ts`
- Create: `mcp-adapter/src/tools/getTaskStatus.ts`
- Create: `mcp-adapter/src/tools/getTaskResult.ts`
- Create: `mcp-adapter/src/tools/cancelTask.ts`

**Acceptance Criteria:**
- Tools return public results only.
- Tool descriptions do not leak workflow.
- Smoke config for Hermes/Cline is documented.

---

## Phase 6: Enterprise Hardening

### Task 6.1: Add auth and tenant policy

**Objective:** Ensure users only see and run authorized capabilities.

**Files:**
- Create: `gateway/app/auth/`
- Create: `gateway/app/capabilities/policy.py`
- Create: `gateway/tests/test_auth_policy.py`

**Acceptance Criteria:**
- Unauthorized users cannot list/run protected capabilities.
- Tenant allowlists are enforced.

### Task 6.2: Add async tasks and audit logs

**Objective:** Support long-running tasks and trace safe metadata.

**Files:**
- Create: `gateway/app/tasks/store.py`
- Create: `gateway/app/tasks/queue.py`
- Create: `gateway/app/audit/`

**Acceptance Criteria:**
- Task statuses: queued/running/completed/failed/cancelled.
- Audit logs record metadata but not raw secrets or skill bodies.

### Task 6.3: Add sandbox runner option

**Objective:** Isolate high-risk capabilities.

**Files:**
- Create: `gateway/app/runners/container_runner.py`
- Create: `docs/deployment.md`

**Acceptance Criteria:**
- Runner can execute in an isolated temp workspace.
- Network and filesystem policy are documented.

---

## PR Roadmap

1. **PR 1:** docs, schemas, examples, repository bootstrap.
2. **PR 2:** Gateway skeleton + health endpoint.
3. **PR 3:** Manifest registry + public capability endpoints.
4. **PR 4:** Mock runner + run endpoint.
5. **PR 5:** Skill-to-capability converter CLI.
6. **PR 6:** Hermes runner + output filter.
7. **PR 7:** VSCode extension skeleton + capability list.
8. **PR 8:** VSCode context collector + report panel.
9. **PR 9:** VSCode patch preview/apply.
10. **PR 10:** MCP adapter skeleton + tools.
11. **PR 11:** Auth/tenant policy.
12. **PR 12:** Async task queue + audit logs.
13. **PR 13:** sandbox runner + deployment docs.

## MVP Definition

MVP is complete when:

- One real private skill is available only on Gateway.
- VSCode extension can call it on current file/diff.
- Extension can show report and apply patch after confirmation.
- MCP adapter can call the same capability.
- No client-facing response contains skill text, prompt, internal manifest, or raw trace.
