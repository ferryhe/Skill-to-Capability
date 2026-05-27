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

每个 capability item 使用 Gateway public view 字段：`id`、`name`、`version`、
`category`、`visible_description`、`input_modes`、`input_schema`、`output_schema`、
`client_permissions`、`approval_policy` 和 public `security` constraints。

不得返回 `internal`、prompt、trace、skill body、`skill_text` 或 server-only manifest 字段。

```json
{
  "capabilities": [
    {
      "id": "backend-rbac-review",
      "name": "Backend RBAC Review",
      "version": "0.1.0",
      "category": "code-review",
      "visible_description": "Review backend RBAC and public API payload boundaries.",
      "input_modes": ["current_file", "selected_files", "git_diff"],
      "input_schema": {
        "type": "object"
      },
      "output_schema": {
        "type": "object"
      },
      "client_permissions": {
        "reads_workspace": true,
        "writes_workspace": "optional",
        "runs_commands": "optional",
        "sends_code_to_server": true
      },
      "approval_policy": {
        "upload_context": "user_confirm_large",
        "apply_patch": "user_confirm",
        "run_commands": "user_confirm"
      },
      "security": {
        "max_files": 20,
        "max_total_input_bytes": 300000,
        "deny_file_globs": [
          "**/.env",
          "**/*.pem",
          "**/*.key",
          "**/id_rsa",
          "**/credentials.json"
        ],
        "allow_file_globs": [
          "**/*.py",
          "**/*.ts",
          "**/*.tsx",
          "**/*.js",
          "**/*.jsx",
          "**/*.md",
          "**/*.json",
          "**/*.yaml",
          "**/*.yml"
        ]
      }
    }
  ]
}
```

## run_capability

MCP tool input wraps the exact Gateway request body under `request`. The adapter uses
`capability_id` to call `/v1/capabilities/{id}/run`; only the nested `request` object is
sent as the Gateway body and must match `run-request.schema.json`.

Adapter tool input:

```json
{
  "capability_id": "backend-rbac-review",
  "request": {
    "workspace": {
      "name": "sample-workspace",
      "root_uri": "file:///workspace/sample-workspace",
      "git_branch": "feat/rbac-tightening",
      "git_diff": "diff --git a/app.py b/app.py\n",
      "files": [
        {
          "path": "app.py",
          "content": "def hello():\n    return 'world'\n"
        }
      ],
      "selection": {
        "path": "app.py",
        "start_line": 1,
        "end_line": 2,
        "content": "def hello():\n    return 'world'\n"
      }
    },
    "instruction": "Review public payload and RBAC boundaries.",
    "options": {
      "return_patch": true,
      "strictness": "high"
    },
    "client": {
      "type": "mcp",
      "version": "0.1.0"
    }
  }
}
```

Exact Gateway request body sent to `/v1/capabilities/backend-rbac-review/run`:

```json
{
  "workspace": {
    "name": "sample-workspace",
    "root_uri": "file:///workspace/sample-workspace",
    "git_branch": "feat/rbac-tightening",
    "git_diff": "diff --git a/app.py b/app.py\n",
    "files": [
      {
        "path": "app.py",
        "content": "def hello():\n    return 'world'\n"
      }
    ],
    "selection": {
      "path": "app.py",
      "start_line": 1,
      "end_line": 2,
      "content": "def hello():\n    return 'world'\n"
    }
  },
  "instruction": "Review public payload and RBAC boundaries.",
  "options": {
    "return_patch": true,
    "strictness": "high"
  },
  "client": {
    "type": "mcp",
    "version": "0.1.0"
  }
}
```

Output returns task metadata plus the public `run-result.schema.json` result fields. It must
not include prompt, trace, skill body, `skill_text`, `internal`, or raw runner output.

```json
{
  "task_id": "task_01H...",
  "status": "completed",
  "summary": "Found one RBAC boundary issue and proposed a focused patch.",
  "findings": [
    {
      "severity": "high",
      "path": "app.py",
      "line": 12,
      "title": "Public endpoint returns sensitive field",
      "message": "The response should omit internal_path for unauthenticated callers."
    }
  ],
  "patch": "diff --git a/app.py b/app.py\n",
  "recommended_tests": [
    "pytest tests/test_rbac.py -q"
  ],
  "artifacts": [],
  "safe_rationale": "The patch removes a sensitive field from the public response.",
  "confidence": 0.82
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
