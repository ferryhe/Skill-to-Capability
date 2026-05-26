# Skill-to-Capability 总体架构

## 背景

传统 agent skill 的常见实现是把 `SKILL.md`、rules 或 prompt 加载进本地 agent context。这个方式灵活，但对高价值业务流程、私有提示词、内部 SOP、客户定制方法论有明显泄露风险。尤其在 Citrix + VSCode 服务场景中，用户 workspace、extension 包、agent context 都不能作为真正的秘密边界。

本项目的目标是把 skill 从“下发给 agent 的文本资产”转换为“后端受控执行的产品能力”。

## 推荐架构

```text
Citrix / user desktop
┌──────────────────────────────┐
│ VSCode Extension             │
│  - login / tenant selection  │
│  - capability list           │
│  - file/diff context picker  │
│  - webview report UI         │
│  - diff preview + apply      │
│  - optional test runner      │
└───────────────┬──────────────┘
                │ HTTPS
┌───────────────▼──────────────┐
│ Skill Gateway                │
│  - auth/license/tenant policy│
│  - capability router         │
│  - input validation/filtering│
│  - private skill registry    │
│  - model/tool orchestration  │
│  - sandboxed runner          │
│  - audit log + result filter │
└───────────────┬──────────────┘
                │
┌───────────────▼──────────────┐
│ Private Runtime              │
│  - private SKILL.md          │
│  - prompts/rubrics           │
│  - internal tools/RAG        │
│  - provider credentials      │
└──────────────────────────────┘

External agent path:
Cline/Roo/Continue/Hermes/Claude Code
  -> MCP Adapter
  -> Skill Gateway
  -> same private runtime
```

## 组件职责

### Skill Gateway

后端唯一可信执行面，负责：

- 加载私有 skill。
- 维护 capability registry。
- 对 capability 做租户和角色授权。
- 验证输入文件、diff、指令和选项。
- 调用 runner 执行工作流。
- 过滤输出，避免内部 prompt / trace / credential 泄露。
- 保存任务状态、审计和 artifact。

### VSCode Extension

薄客户端，负责：

- 登录和配置 Gateway URL。
- 展示用户可用 capabilities。
- 收集当前文件、选中文件、selection、git diff 等最小上下文。
- 调用 Gateway。
- 展示 report/findings。
- 预览 patch。
- 用户确认后修改 workspace。
- 用户确认后运行 recommended tests。

### MCP Adapter

Agent 兼容层，负责：

- 暴露小而稳定的 MCP tool surface。
- 把 MCP calls 转发到 Gateway。
- 把结果转换成 MCP text / resource 响应。
- 不暴露 skill 原文、internal manifest、prompt 或完整 trace。

## 数据流

### VSCode 调用流程

```text
User selects files/diff
  -> Extension fetches capability metadata
  -> Extension collects minimal workspace context
  -> POST /v1/capabilities/{id}/run
  -> Gateway validates auth/policy/input
  -> Gateway privately loads skill and executes runner
  -> Gateway filters result
  -> Extension renders report
  -> Extension previews patch
  -> User approves apply
  -> Extension modifies workspace files
  -> Optional user-approved test command
```

### MCP 调用流程

```text
Agent calls list_capabilities
  -> MCP Adapter calls Gateway /capabilities
  -> Agent sees public capability names/descriptions only

Agent calls run_capability
  -> MCP Adapter forwards files/diff/instruction to Gateway
  -> Gateway runs private skill
  -> MCP Adapter returns summary/findings/patch/recommended_tests
```

## 重要非目标

第一阶段不做：

- 完整多 agent orchestration 平台。
- Web IDE。
- 自动支持所有 side-effect skills。
- 让客户端直接读取或解释 skill。
- 在 VSIX / CLI 中打包私有 prompt。

## 推荐技术栈

- Gateway: Python, FastAPI, Pydantic, SQLite/Postgres, background worker。
- VSCode: TypeScript, VSCode API, Webview, WorkspaceEdit。
- MCP Adapter: TypeScript MCP SDK 或 Python MCP SDK。
- Schemas: JSON Schema + Pydantic models。
- Runner: MVP 使用 mock runner + Hermes subprocess runner；后续可演进为 SDK/internal API/container runner。
