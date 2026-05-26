# Skill-to-Capability 全量开发推进计划

> 这个文档是项目级执行路线图。目标是把当前架构文档推进成可运行、可测试、可发布的产品：Skill Gateway 后端、VSCode Extension、MCP Adapter 三条线同时成型，但每次 PR 保持单一范围、可验证、可回滚。

## 1. 最终交付目标

项目完成时，应具备以下能力：

1. **Skill Gateway 后端**
   - 私有加载 `SKILL.md` / prompt / rubric。
   - 将 skill 暴露为 public capability，而不是暴露 skill 文本。
   - 支持 capability manifest 注册、权限策略、输入过滤、runner 执行、任务状态、审计日志、输出脱敏。
   - 至少支持 `mock`、`hermes` 两类 runner；后续支持 container/sandbox runner。

2. **VSCode Extension**
   - 用户可配置 Gateway URL 并登录。
   - 可列出当前用户可用 capabilities。
   - 可从当前文件、选中文件、selection、git diff 收集上下文。
   - 可调用 capability，展示 report/findings。
   - 可预览 patch，用户确认后修改 workspace。
   - 可展示 recommended tests，用户确认后运行。

3. **MCP Adapter**
   - 以 stdio MCP server 形式暴露能力给 Cline/Roo/Continue/Hermes/Claude Code 等 agent。
   - 只提供 `list_capabilities`、`run_capability`、`get_task_status`、`get_task_result`、`cancel_task`。
   - 不提供任何 raw skill retrieval。

4. **安全和企业化能力**
   - 客户端永远拿不到 `internal` manifest、skill 原文、prompt、完整 trace、provider key。
   - 默认拒绝 `.env`、`*.pem`、`id_rsa`、`credentials.json` 等敏感文件上传。
   - 默认写文件和执行命令都需要用户确认。
   - 审计日志记录 task metadata，不记录 skill body 或原始 secret。
   - 有 prompt injection、path traversal、output leakage 的回归测试。

## 2. 开发方式：沿用“老办法”

每个阶段按以下固定循环推进：

```text
sync main
  -> create narrow task branch
  -> implement with TDD where code behavior changes
  -> focused tests
  -> full relevant tests
  -> static/security checks
  -> Codex CLI review diff
  -> fix accepted in-scope findings
  -> commit
  -> push
  -> open PR
  -> wait/check remote CI + inline comments
  -> fix confirmed comments only
  -> merge
  -> sync main
  -> next branch
```

### 2.1 每个 PR 的范围规则

- 一个 PR 只解决一个层面的能力：schema、gateway endpoint、runner、extension UI、MCP tool、auth、audit 等不要混在一起。
- 每个 PR 必须能独立验证。
- 不把“顺手优化”混进当前 PR。
- 不在客户端引入任何私有 skill 文本。
- 不为了 demo 绕过安全边界。

### 2.2 每个 PR 的本地验证规则

文档/Schema PR：

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate-contracts.py
python3 -m json.tool schemas/capability.schema.json >/dev/null
python3 -m json.tool schemas/run-request.schema.json >/dev/null
python3 -m json.tool schemas/run-result.schema.json >/dev/null
git diff --check
```

Gateway PR：

```bash
cd gateway
python -m pytest tests/ -q
python -m ruff check .
python -m mypy app
```

VSCode Extension PR：

```bash
cd vscode-extension
npm install
npm run compile
npm test -- --runInBand || npm test
```

MCP Adapter PR：

```bash
cd mcp-adapter
npm install
npm run build
npm test
```

全仓集成 PR：

```bash
python3 -m json.tool schemas/capability.schema.json >/dev/null
python3 -m json.tool schemas/run-request.schema.json >/dev/null
python3 -m json.tool schemas/run-result.schema.json >/dev/null
(cd gateway && python -m pytest tests/ -q)
(cd vscode-extension && npm run compile && npm test)
(cd mcp-adapter && npm run build && npm test)
```

### 2.3 Review gate

提交前运行：

```bash
codex -c 'model="gpt-5.5"' review --uncommitted
```

只接受：

- 正确性问题；
- 安全边界问题；
- schema/API contract 不一致；
- 测试缺口；
- 当前 PR 范围内的确定 bug。

不接受：

- 大范围重构建议；
- 命名风格偏好；
- 与当前 PR 无关的架构扩展；
- 会改变已定安全边界的“简化建议”。

如果 Codex 不可用，替代方案是独立 review：spec compliance + code quality，两轮都过才提交。

## 3. 里程碑和 PR 切分

## Milestone A：项目契约冻结

目标：把 shared contracts 定下来，后续 Gateway / VSCode / MCP 都按这个 contract 开发。

### PR A1：Schema 和示例 fixtures 完整化

**范围**
- 完善 `schemas/capability.schema.json`。
- 完善 `schemas/run-request.schema.json`。
- 完善 `schemas/run-result.schema.json`。
- 新增 JSON/YAML fixtures：valid/invalid capability、valid run request、valid run result。

**建议文件**
```text
schemas/*.json
tests/contracts/fixtures/valid-capability.yaml
tests/contracts/fixtures/invalid-capability-leaks-internal.yaml
tests/contracts/fixtures/run-request-current-file.json
tests/contracts/fixtures/run-result-with-patch.json
scripts/validate-contracts.py
```

**验收**
```bash
python3 scripts/validate-contracts.py
```

**完成标准**
- valid fixtures 全部通过。
- invalid fixtures 明确失败。
- `internal.expose_skill_text` 只能是 `false`。
- result schema 不允许 `prompt`、`trace`、`skill_text`。

### PR A2：文档 contract 对齐

**范围**
- 让 `docs/api-contract.md`、`docs/vscode-extension.md`、`docs/mcp-adapter.md` 与 schema 字段完全一致。
- 增加“public view 和 internal view”示例。

**验收**
```bash
git diff --check
python3 scripts/validate-contracts.py
```

**完成标准**
- 文档中的字段名和 schema 一致。
- 所有 copy-paste JSON 示例可解析。

## Milestone B：Gateway 最小可运行后端

目标：先不要接真实 LLM，跑通 capability registry -> mock runner -> result filter。

### PR B1：FastAPI Gateway skeleton

**范围**
- 建立 `gateway/` Python 项目。
- `/health` endpoint。
- 测试框架。

**建议文件**
```text
gateway/pyproject.toml
gateway/app/main.py
gateway/app/api/health.py
gateway/tests/test_health.py
```

**验收**
```bash
cd gateway
python -m pytest tests/ -q
python - <<'PY'
from gateway.app.main import app
assert app is not None
PY
```

### PR B2：Capability manifest registry

**范围**
- Pydantic model。
- YAML loader。
- public view stripping。
- `GET /v1/capabilities`。
- `GET /v1/capabilities/{id}`。

**建议文件**
```text
gateway/app/capabilities/manifest.py
gateway/app/capabilities/registry.py
gateway/app/api/capabilities.py
gateway/capabilities/backend-rbac-review.yaml
gateway/tests/test_capability_registry.py
gateway/tests/test_capability_api.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_capability_registry.py tests/test_capability_api.py -q
```

**完成标准**
- API response 不包含 `internal`、`skill_ref`、`model_policy`。
- unknown capability 返回 404。
- invalid manifest 启动或加载时报错。

### PR B3：Input policy 和 security denylist

**范围**
- 文件路径校验。
- deny file globs。
- byte limits。
- secret-like content 初步拒绝或标记。

**建议文件**
```text
gateway/app/security/path_policy.py
gateway/app/security/input_policy.py
gateway/tests/test_input_policy.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_input_policy.py -q
```

**完成标准**
- 拒绝 `../escape.py`。
- 拒绝 absolute path。
- 拒绝 `.env`、`*.pem`、`id_rsa`。
- 超过 max files / max bytes 会失败。

### PR B4：Mock runner + run endpoint

**范围**
- runner interface。
- mock runner。
- `POST /v1/capabilities/{id}/run`。
- 同步 task result。

**建议文件**
```text
gateway/app/runners/base.py
gateway/app/runners/mock_runner.py
gateway/app/tasks/models.py
gateway/app/api/capabilities.py
gateway/tests/test_run_capability.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_run_capability.py -q
```

**完成标准**
- valid request 返回 summary/findings/patch/recommended_tests。
- denied file request 返回 policy error。
- result 不含 prompt/trace/skill_text/internal。

### PR B5：Output filter 和 redaction

**范围**
- token/key/path 脱敏。
- 禁止输出疑似 skill body / internal prompt。
- 错误响应统一 shape。

**建议文件**
```text
gateway/app/security/redaction.py
gateway/app/security/output_filter.py
gateway/app/api/errors.py
gateway/tests/test_output_filter.py
gateway/tests/test_error_redaction.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_output_filter.py tests/test_error_redaction.py -q
```

**完成标准**
- Bearer token / API key / private path 被 redacted。
- 模拟 prompt injection 输出 skill 原文会被过滤或拒绝。

## Milestone C：Skill-to-Capability 转换器

目标：把任意 `SKILL.md` 转成 capability draft，但不复制 skill body。

### PR C1：SKILL.md parser 和 converter

**范围**
- 解析 frontmatter。
- 生成 manifest draft。
- `internal.skill_ref` 指向 skill name。
- `internal.expose_skill_text = false`。

**建议文件**
```text
gateway/app/skills/converter.py
gateway/app/skills/frontmatter.py
gateway/tests/test_skill_converter.py
examples/skills/backend-rbac-review/SKILL.md
```

**验收**
```bash
cd gateway
python -m pytest tests/test_skill_converter.py -q
```

**完成标准**
- 生成 manifest 可被 registry 加载。
- manifest 不包含 skill body。

### PR C2：skillgw CLI

**范围**
- `skillgw capabilities generate`。
- `skillgw capabilities validate`。
- `skillgw capabilities list`。

**建议文件**
```text
gateway/app/cli.py
gateway/tests/test_cli.py
```

**验收**
```bash
cd gateway
skillgw capabilities validate gateway/capabilities/backend-rbac-review.yaml
skillgw capabilities generate --skill ../examples/skills/backend-rbac-review/SKILL.md --out /tmp/backend-rbac-review.yaml
```

**完成标准**
- CLI 对 invalid manifest 返回非 0。
- CLI 输出不包含 skill body。

## Milestone D：真实 Runner 和任务生命周期

目标：从 mock runner 走向真实 server-side skill execution。

### PR D1：Hermes runner contract

**范围**
- 先不强依赖本机 Hermes；实现可 mock 的 subprocess runner contract。
- 统一 strict JSON output parser。

**建议文件**
```text
gateway/app/runners/hermes_runner.py
gateway/app/runners/json_output.py
gateway/tests/test_hermes_runner_contract.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_hermes_runner_contract.py -q
```

**完成标准**
- JSON parse 失败会安全失败或重试。
- runner result 一定经过 schema validation 和 output filter。

### PR D2：Task store 和异步状态

**范围**
- task model。
- in-memory 或 SQLite task store。
- queued/running/completed/failed/cancelled。
- `GET /v1/tasks/{task_id}`。
- `GET /v1/tasks/{task_id}/result`。
- `POST /v1/tasks/{task_id}/cancel`。

**建议文件**
```text
gateway/app/tasks/store.py
gateway/app/tasks/queue.py
gateway/app/api/tasks.py
gateway/tests/test_tasks_api.py
```

**验收**
```bash
cd gateway
python -m pytest tests/test_tasks_api.py -q
```

**完成标准**
- run endpoint 可返回 queued task。
- task result 可查询。
- failed task 错误脱敏。

### PR D3：真实 Hermes smoke

**范围**
- 在开发环境中用一个非敏感示例 skill 跑通 Hermes runner。
- 写 smoke script，不把真实私有 skill 放进 repo。

**建议文件**
```text
gateway/scripts/smoke_hermes_runner.py
docs/development.md
```

**验收**
```bash
cd gateway
python scripts/smoke_hermes_runner.py --capability backend-rbac-review --sample ../examples/sample-workspace
```

**完成标准**
- smoke 输出合法 run-result JSON。
- repo 里没有真实敏感 skill。

## Milestone E：VSCode Extension MVP

目标：普通用户可以在 VSCode 中调用 Gateway capability，并安全 apply patch。

### PR E1：Extension skeleton + settings + auth placeholder

**范围**
- extension activate。
- settings。
- secret storage token placeholder。
- Gateway client。

**建议文件**
```text
vscode-extension/package.json
vscode-extension/tsconfig.json
vscode-extension/src/extension.ts
vscode-extension/src/api/client.ts
vscode-extension/src/auth/session.ts
```

**验收**
```bash
cd vscode-extension
npm install
npm run compile
```

### PR E2：Capability list UI

**范围**
- command palette 刷新 capability。
- sidebar/tree provider。
- capability detail view。

**建议文件**
```text
vscode-extension/src/capabilities/treeProvider.ts
vscode-extension/src/commands/refreshCapabilities.ts
```

**验收**
- 用本地 Gateway mock server 能列出 `backend-rbac-review`。
- UI 不显示 internal 字段。

### PR E3：Workspace context collector

**范围**
- current file。
- selected files。
- selection。
- git diff。
- denylist/size policy。

**建议文件**
```text
vscode-extension/src/context/workspaceCollector.ts
vscode-extension/src/context/policy.ts
vscode-extension/src/test/workspaceCollector.test.ts
```

**验收**
```bash
cd vscode-extension
npm test -- workspaceCollector
```

**完成标准**
- `.env` 不会上传。
- 超大文件不会上传。
- git diff 可读取或优雅报错。

### PR E4：Run capability + report panel

**范围**
- 用户选择 capability。
- 输入 instruction。
- 调 Gateway。
- webview 展示 summary/findings/recommended tests。

**建议文件**
```text
vscode-extension/src/commands/runCapability.ts
vscode-extension/src/webview/reportPanel.ts
```

**验收**
- 连接本地 Gateway mock runner，能显示 report。
- 即使 server 返回 internal 字段，UI 也忽略。

### PR E5：Patch preview/apply

**范围**
- 支持 unified diff 或 file replacement edits。
- preview diff。
- apply with VSCode WorkspaceEdit。
- workspace path safety check。

**建议文件**
```text
vscode-extension/src/patch/diffPreview.ts
vscode-extension/src/patch/applyPatch.ts
vscode-extension/src/test/applyPatch.test.ts
```

**验收**
```bash
cd vscode-extension
npm test -- applyPatch
```

**完成标准**
- patch 不能写 workspace 外。
- apply 前用户确认。
- apply 后 git diff 能看到变化。

### PR E6：Recommended tests execution

**范围**
- 展示 recommended tests。
- 用户确认后在 VSCode terminal 执行。
- 不自动执行。

**建议文件**
```text
vscode-extension/src/commands/runRecommendedTests.ts
```

**验收**
- 点击 test command 前有 confirm。
- command 在 workspace root terminal 执行。

## Milestone F：MCP Adapter MVP

目标：Cline/Roo/Hermes 等 agent 能调用同一 Gateway capability。

### PR F1：MCP server skeleton

**范围**
- TypeScript MCP server。
- Gateway client。
- config/env handling。

**建议文件**
```text
mcp-adapter/package.json
mcp-adapter/tsconfig.json
mcp-adapter/src/server.ts
mcp-adapter/src/gatewayClient.ts
```

**验收**
```bash
cd mcp-adapter
npm install
npm run build
```

### PR F2：list/run/status/result/cancel tools

**范围**
- `list_capabilities`。
- `run_capability`。
- `get_task_status`。
- `get_task_result`。
- `cancel_task`。

**建议文件**
```text
mcp-adapter/src/tools/listCapabilities.ts
mcp-adapter/src/tools/runCapability.ts
mcp-adapter/src/tools/getTaskStatus.ts
mcp-adapter/src/tools/getTaskResult.ts
mcp-adapter/src/tools/cancelTask.ts
mcp-adapter/src/tools/index.ts
```

**验收**
```bash
cd mcp-adapter
npm test
npm run build
```

**完成标准**
- tool descriptions 不泄露内部 workflow。
- tool output 不含 `internal`。

### PR F3：Hermes/Cline smoke docs

**范围**
- MCP 配置示例。
- 本地 Gateway + MCP adapter smoke。

**建议文件**
```text
docs/mcp-smoke.md
examples/mcp/hermes-config.yaml
examples/mcp/cline-config.json
```

**验收**
- Hermes 可配置 stdio MCP server。
- Cline/Roo 可参考配置接入。

## Milestone G：Auth、Tenant、Audit、安全强化

目标：从 demo 变成企业可试点。

### PR G1：Token auth 和 tenant identity

**范围**
- API token auth。
- user/tenant context。
- local dev bypass only under explicit setting。

**建议文件**
```text
gateway/app/auth/models.py
gateway/app/auth/dependencies.py
gateway/tests/test_auth.py
```

**验收**
- 无 token 不能访问 protected capabilities。
- dev mode 行为显式可见，不默认生产开启。

### PR G2：Capability policy

**范围**
- tenant allowlist。
- role-based capability run permissions。
- public listing 只显示有权限的能力。

**建议文件**
```text
gateway/app/capabilities/policy.py
gateway/tests/test_capability_policy.py
```

**验收**
- tenant A 看不到 tenant B capability。
- viewer 只能 readonly，developer 可 request patch。

### PR G3：Audit log

**范围**
- task audit event。
- input metadata。
- output metadata。
- approval events。
- no raw skill/no raw secret。

**建议文件**
```text
gateway/app/audit/models.py
gateway/app/audit/store.py
gateway/tests/test_audit_log.py
```

**验收**
- audit 可查 task lifecycle。
- audit 不含 skill body 或 full prompt。

### PR G4：Security regression suite

**范围**
- prompt injection。
- internal leakage。
- file traversal。
- secret upload。
- error redaction。

**建议文件**
```text
gateway/tests/security/test_no_skill_leakage.py
gateway/tests/security/test_prompt_injection.py
gateway/tests/security/test_path_traversal.py
gateway/tests/security/test_secret_upload.py
```

**验收**
```bash
cd gateway
python -m pytest tests/security -q
```

## Milestone H：端到端闭环和发布准备

目标：三件东西一起跑通：Gateway + VSCode + MCP。

### PR H1：Local dev compose / scripts

**范围**
- 一键启动 Gateway。
- mock capability smoke。
- extension dev instructions。
- MCP adapter dev instructions。

**建议文件**
```text
Makefile
scripts/dev-gateway.sh
scripts/smoke-http.sh
docs/development.md
```

**验收**
```bash
make test
make smoke
```

### PR H2：End-to-end sample workspace

**范围**
- 示例 workspace。
- 一个模拟 RBAC bug。
- Gateway mock/hermes 返回 patch。
- VSCode apply patch 后测试通过。

**建议文件**
```text
examples/sample-workspace/
docs/e2e-smoke.md
```

**验收**
- 从 docs 按步骤可以跑通完整链路。

### PR H3：CI

**范围**
- GitHub Actions。
- schema validation。
- gateway tests。
- extension build/tests。
- MCP build/tests。

**建议文件**
```text
.github/workflows/ci.yml
```

**验收**
- PR 自动跑 CI。
- 失败能定位到 gateway/vscode/mcp/schema。

### PR H4：Release packaging

**范围**
- Gateway Dockerfile。
- VSIX packaging。
- MCP npm package skeleton。
- deployment docs。

**建议文件**
```text
gateway/Dockerfile
vscode-extension/.vscodeignore
mcp-adapter/README.md
docs/deployment.md
```

**验收**
- Gateway image 可 build。
- VSIX 可 package。
- MCP package 可 local install。

## 4. Controller 工作方式

推进整个项目时，controller 保持以下状态文件：

```text
docs/project-status.md
```

每次 PR 合并后更新：

- 当前 milestone。
- 已完成 PR。
- 当前开放 PR。
- 下一步 branch。
- 验证命令。
- 风险/阻塞。

建议格式：

```markdown
# Project Status

## Current Milestone
B: Gateway MVP

## Completed
- PR A1: Schema fixtures
- PR A2: Contract docs

## Current Branch
feat/gateway-health

## Next PR
B2: Capability manifest registry

## Required Verification
- cd gateway && python -m pytest tests/ -q

## Risks
- Hermes runner integration not started
```

## 5. Definition of Done

### 单个 PR Done

- [ ] Scope 单一。
- [ ] 有测试或明确说明为何是 docs-only。
- [ ] Focused tests 通过。
- [ ] Relevant full tests 通过。
- [ ] `git diff --check` 通过。
- [ ] 无 secret-like 内容。
- [ ] Codex review 无必须修复问题，或已修复。
- [ ] PR 描述包含 Summary / Test Plan / Security Notes。
- [ ] 远端 comments 已检查，只修确认成立且 scope 内的问题。

### Milestone Done

- [ ] 该 milestone 所有 PR 已合并。
- [ ] `docs/project-status.md` 更新。
- [ ] 端到端 smoke 至少覆盖该 milestone 的新增路径。
- [ ] 没有 open blocker。

### 全项目 Done

- [ ] Gateway 可本地启动并跑 mock + Hermes runner。
- [ ] VSCode extension 可列 capability、收集上下文、展示 report、apply patch、运行 recommended tests。
- [ ] MCP adapter 可被 Hermes/Cline 调用。
- [ ] 安全测试覆盖 no skill leakage、prompt injection、path traversal、secret upload、error redaction。
- [ ] CI 覆盖 schema/gateway/vscode/mcp。
- [ ] docs 包含 development、deployment、e2e smoke、MCP smoke。
- [ ] 示例 capability 完整跑通。

## 6. 推荐优先级

如果资源有限，先按这个顺序：

```text
A1/A2 contracts
B1-B5 Gateway mock MVP
C1/C2 converter
E1-E5 VSCode MVP
F1-F2 MCP MVP
D1-D3 Hermes runner
G security hardening
H CI/release/e2e
```

原因：先把 Gateway + mock 跑通，VSCode/MCP 都能基于稳定 API 并行开发；Hermes runner 是真实价值入口，但不能早于 contract/security filter，否则容易把私有 skill 泄露到错误位置。

## 7. 第一周建议执行顺序

1. PR A1：Schema fixtures + validator。
2. PR B1：Gateway health。
3. PR B2：Manifest registry + public API。
4. PR B4：Mock runner + run endpoint。
5. PR E1：VSCode skeleton。
6. PR F1：MCP skeleton。

第一周结束时，应该可以做到：

```text
curl Gateway /capabilities
curl Gateway /run -> mock result
VSCode extension 可以列 capabilities
MCP server 可以启动并连接 Gateway client
```

这就是后续所有真实 skill execution 的地基。
