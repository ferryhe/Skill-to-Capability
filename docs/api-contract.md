# Skill Gateway API Contract

Base path: `/v1`

## GET /health

返回服务健康状态。

```json
{
  "status": "ok"
}
```

## GET /capabilities

返回当前用户可见的 public capability list。

必须不包含 `internal` 字段。

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
      "client_permissions": {
        "reads_workspace": true,
        "writes_workspace": "optional",
        "runs_commands": "optional",
        "sends_code_to_server": true
      }
    }
  ]
}
```

## GET /capabilities/{id}

返回一个 public capability detail。不得返回 `internal`。

## POST /capabilities/{id}/run

同步或异步启动 capability。

Request:

```json
{
  "workspace": {
    "name": "example-repo",
    "git_branch": "feature/x",
    "git_diff": "diff --git ...",
    "files": [
      {
        "path": "src/foo.py",
        "content": "print('hello')\n"
      }
    ],
    "selection": {
      "path": "src/foo.py",
      "start_line": 1,
      "end_line": 1,
      "content": "print('hello')"
    }
  },
  "instruction": "Review this file",
  "options": {
    "return_patch": true,
    "strictness": "normal"
  },
  "client": {
    "type": "vscode",
    "version": "0.1.0"
  }
}
```

Response:

```json
{
  "task_id": "task_01H...",
  "status": "completed",
  "result": {
    "summary": "No issues found.",
    "findings": [],
    "patch": null,
    "recommended_tests": [],
    "artifacts": [],
    "safe_rationale": "The inspected route is read-only and does not expose sensitive fields."
  }
}
```

Long-running tasks may return:

```json
{
  "task_id": "task_01H...",
  "status": "queued"
}
```

## GET /tasks/{task_id}

返回任务状态。

```json
{
  "task_id": "task_01H...",
  "status": "running",
  "capability_id": "backend-rbac-review",
  "created_at": "2026-05-26T00:00:00Z",
  "updated_at": "2026-05-26T00:00:05Z"
}
```

## GET /tasks/{task_id}/result

返回任务结果。不得返回 prompt/skill/trace。

## POST /tasks/{task_id}/cancel

取消任务。

## Error shape

```json
{
  "error": {
    "code": "input_policy_violation",
    "message": "The request includes a denied file type.",
    "details": {
      "path": "[REDACTED]"
    }
  }
}
```

错误必须脱敏。
