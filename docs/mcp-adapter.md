# MCP Adapter Contract

## 目标

让 Cline、Roo Code、Continue、Claude Code、Hermes、Copilot Agent 等通过 MCP 调用同一套 Skill Gateway capabilities，同时不暴露私有 skill。

## Transport

MVP 使用 stdio MCP server：

```bash
company-skill-mcp --gateway-url https://gateway.example.com
```

Token 来源优先：

- environment variable
- keychain/secret storage
- config file with restricted permissions

## Tools

MVP 只暴露 5 个工具：

```text
list_capabilities
run_capability
get_task_status
get_task_result
cancel_task
```

## list_capabilities

返回 public capability list。

不得返回 `internal`。

## run_capability

Input:

```json
{
  "capability_id": "backend-rbac-review",
  "instruction": "Review current diff",
  "files": [
    {
      "path": "src/foo.py",
      "content": "..."
    }
  ],
  "diff": "diff --git ...",
  "options": {
    "return_patch": true
  }
}
```

Output:

```json
{
  "task_id": "task_01H...",
  "status": "completed",
  "summary": "...",
  "findings": [],
  "patch": "diff --git ...",
  "recommended_tests": []
}
```

## Tool description policy

MCP tool description 应该说明能力结果，不应描述内部执行方法。

Bad:

```text
Uses our proprietary 9-step RBAC review prompt and internal rubric...
```

Good:

```text
Runs an approved company capability on provided workspace context and returns a report, optional patch, and recommended tests.
```

## Compatibility targets

- Cline / Roo Code: local stdio MCP config。
- Hermes: `mcp_servers` stdio 或 HTTP config。
- Continue / Claude Code / Copilot Agent: follow their MCP integration once available/stable。

## Security requirements

- No raw skill retrieval tool。
- No internal manifest in responses。
- Redact Gateway errors before returning to agent。
- Cap output size and use artifacts for large reports。
- Never ask agent to store provider credentials。
