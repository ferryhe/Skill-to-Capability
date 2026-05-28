# Skill-to-Capability

把私有 AI `SKILL.md` / runbook / prompt 工作流包装成安全的产品能力：后端保留 skill 和 prompt，客户端只看到 capability，并通过 VSCode Extension 或 MCP Adapter 调用。

## 一句话架构

```text
Private SKILL.md / workflow
  -> Capability Manifest
  -> Skill Gateway 后端
  -> HTTP API
  -> VSCode Extension
  -> MCP Adapter
  -> Report / Patch / Recommended Tests
```

## 核心原则

- **skill 原文不下发**：不要把高价值 skill 放进 VSIX、npm 包、本地 CLI、Citrix 用户文件系统或 agent context。
- **能力公开，流程私有**：用户看到 `Backend RBAC Review` 这类 capability，不看到背后的 prompt、rubric、工具编排和私有知识库。
- **客户端薄，后端厚**：VSCode extension 负责收集上下文、调用 gateway、展示报告、预览并应用 patch；Skill Gateway 负责私有 skill 执行。
- **同一能力多入口**：VSCode extension、MCP Adapter、未来 CLI/Web UI 都调用同一套 Gateway API。
- **默认人工确认写操作**：推荐 `Analyze -> Preview Diff -> Apply -> Optional Test`，不要默认静默改 workspace。

## 目标组件

```text
skill-capability-platform/
├─ gateway/              # FastAPI Skill Gateway：auth、capability registry、private runner、policy、audit
├─ vscode-extension/     # VSCode thin client：capability list、context collector、report UI、diff/apply
├─ mcp-adapter/          # MCP server：让 Cline/Roo/Continue/Hermes/Claude Code 调同一能力
├─ schemas/              # capability / request / result JSON Schema
├─ docs/                 # 架构、安全、API、开发计划
└─ examples/             # 示例 skill 与 capability manifest
```

## 当前状态

本仓库先建立产品架构、接口契约和开发计划。第一阶段建议以一个真实私有 skill 做闭环验证：

```text
SKILL.md -> capability manifest -> gateway run -> VSCode report -> patch apply -> MCP run
```

## 本地验证

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate-contracts.py
```

## 文档入口

- [总体架构](docs/architecture.md)
- [安全模型](docs/security-model.md)
- [Capability Authoring](docs/capability-authoring.md)
- [API Contract](docs/api-contract.md)
- [VSCode Extension Contract](docs/vscode-extension.md)
- [MCP Adapter Contract](docs/mcp-adapter.md)
- [MCP Smoke](docs/mcp-smoke.md)
- [H2 E2E Smoke](docs/e2e-smoke.md)
- [Deployment](docs/deployment.md)
- [开发计划](docs/plans/skill-capability-platform.md)
- [全量开发推进路线图](docs/development-roadmap.md)
- [项目状态](docs/project-status.md)

## MVP 成功标准

第一版不是“支持所有 skill”，而是证明：

> 一个真实私有 skill 可以在后端执行，VSCode 可以像调用普通产品功能一样使用它，MCP agent 也可以调用它，但任何客户端都拿不到 skill 原文。
