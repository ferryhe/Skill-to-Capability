# Capability Authoring

## 概念

Capability 是私有 skill 的产品化公开接口。它描述“用户能调用什么能力、需要什么输入、会得到什么输出”，但不描述内部 prompt、rubric 和执行流程。

## Manifest 分层

### Public fields

可返回给 VSCode / MCP client：

- `id`
- `name`
- `version`
- `category`
- `visible_description`
- `input_modes`
- `input_schema`
- `output_schema`
- `client_permissions`
- `approval_policy` 的 public view
- `security` 的 public constraints

### Internal fields

只保存在 Gateway：

- `internal.skill_ref`
- `internal.runner`
- `internal.model_policy`
- `internal.required_env`
- `internal.required_commands`
- `internal.expose_skill_text`
- private prompt and rubric references

## 示例 Manifest

见 [`examples/capabilities/backend-rbac-review.yaml`](../examples/capabilities/backend-rbac-review.yaml)。

## Skill-to-Capability 转换规则

从 `SKILL.md` frontmatter 自动提取：

```text
name -> id
name -> internal.skill_ref
description -> visible_description
tags -> category / labels
required_environment_variables -> internal.required_env
required_commands -> internal.required_commands
```

默认生成：

```yaml
input_modes:
  - current_file
  - selected_files
  - git_diff

client_permissions:
  reads_workspace: true
  writes_workspace: optional
  runs_commands: optional
  sends_code_to_server: true

internal:
  runner: hermes
  expose_skill_text: false
```

转换器不得把 skill body 写入 public manifest。

## Skill 类型

### Readonly Advisory

只读分析，输出报告。最容易转换。

### Patch-Producing

输出 patch，需要 VSCode diff preview 和用户确认 apply。

### Command-Recommending

输出 recommended tests / commands，需要用户确认执行。

### External-Side-Effect

发送消息、邮件、开 PR、部署、写数据库等。必须有强权限和审计，MVP 不默认支持。

## Runner 输出契约

所有 runner 都必须输出统一结构：

```json
{
  "summary": "string",
  "findings": [],
  "patch": null,
  "recommended_tests": [],
  "artifacts": [],
  "safe_rationale": "string"
}
```

不能直接把模型原始输出转发给 client。Gateway 必须 validate / repair / reject。
