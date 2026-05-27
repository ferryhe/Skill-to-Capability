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

Public capability view 来自 manifest allowlist。必须不包含 `internal` 字段，也不得包含
prompt、trace、skill body、`skill_text` 或 server-only manifest 字段。

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
        "type": "object",
        "required": ["instruction"],
        "properties": {
          "instruction": {
            "type": "string",
            "maxLength": 4000
          },
          "files": {
            "type": "array",
            "maxItems": 20,
            "items": {
              "type": "object",
              "required": ["path", "content"],
              "properties": {
                "path": {
                  "type": "string"
                },
                "content": {
                  "type": "string",
                  "maxLength": 50000
                }
              }
            }
          },
          "diff": {
            "type": "string",
            "maxLength": 200000
          },
          "options": {
            "type": "object",
            "additionalProperties": true
          }
        }
      },
      "output_schema": {
        "type": "object",
        "required": ["summary"],
        "properties": {
          "summary": {
            "type": "string"
          },
          "findings": {
            "type": "array"
          },
          "patch": {
            "type": ["string", "null"]
          },
          "recommended_tests": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "artifacts": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": true
            }
          },
          "safe_rationale": {
            "type": "string"
          },
          "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          }
        }
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

## GET /capabilities/{id}

返回一个 public capability detail，字段 shape 与 list item 一致。不得返回 `internal`、
prompt、trace、skill body、`skill_text` 或 server-only manifest 字段。

Endpoint response example:

```json
{
  "id": "backend-rbac-review",
  "name": "Backend RBAC Review",
  "version": "0.1.0",
  "category": "code-review",
  "visible_description": "Review backend RBAC and public API payload boundaries.",
  "input_modes": ["current_file", "selected_files", "git_diff"],
  "input_schema": {
    "type": "object",
    "required": ["instruction"],
    "properties": {
      "instruction": {
        "type": "string",
        "maxLength": 4000
      },
      "files": {
        "type": "array",
        "maxItems": 20,
        "items": {
          "type": "object",
          "required": ["path", "content"],
          "properties": {
            "path": {
              "type": "string"
            },
            "content": {
              "type": "string",
              "maxLength": 50000
            }
          }
        }
      },
      "diff": {
        "type": "string",
        "maxLength": 200000
      },
      "options": {
        "type": "object",
        "additionalProperties": true
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["summary"],
    "properties": {
      "summary": {
        "type": "string"
      },
      "findings": {
        "type": "array"
      },
      "patch": {
        "type": ["string", "null"]
      },
      "recommended_tests": {
        "type": "array",
        "items": {
          "type": "string"
        }
      },
      "artifacts": {
        "type": "array",
        "items": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "safe_rationale": {
        "type": "string"
      },
      "confidence": {
        "type": "number",
        "minimum": 0,
        "maximum": 1
      }
    }
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
```

### Server-only manifest view

Gateway 内部保存的 full manifest 可以包含 server-only `internal` 字段，但该 view
只允许存在于 Gateway 进程、私有配置和 server-side validation 中，不能作为
`GET /capabilities/{id}` 响应返回：

```json
{
  "id": "backend-rbac-review",
  "name": "Backend RBAC Review",
  "version": "0.1.0",
  "category": "code-review",
  "visible_description": "Review backend RBAC and public API payload boundaries.",
  "input_modes": ["current_file", "selected_files", "git_diff"],
  "input_schema": {
    "type": "object",
    "required": ["instruction"],
    "properties": {
      "instruction": {
        "type": "string",
        "maxLength": 4000
      },
      "files": {
        "type": "array",
        "maxItems": 20,
        "items": {
          "type": "object",
          "required": ["path", "content"],
          "properties": {
            "path": {
              "type": "string"
            },
            "content": {
              "type": "string",
              "maxLength": 50000
            }
          }
        }
      },
      "diff": {
        "type": "string",
        "maxLength": 200000
      },
      "options": {
        "type": "object",
        "additionalProperties": true
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["summary"],
    "properties": {
      "summary": {
        "type": "string"
      },
      "findings": {
        "type": "array"
      },
      "patch": {
        "type": "string"
      },
      "recommended_tests": {
        "type": "array",
        "items": {
          "type": "string"
        }
      },
      "artifacts": {
        "type": "array"
      },
      "safe_rationale": {
        "type": "string"
      }
    }
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
  "internal": {
    "skill_ref": "backend-rbac-review",
    "runner": "hermes",
    "model_policy": "high_reasoning",
    "expose_skill_text": false
  }
}
```

## POST /capabilities/{id}/run

同步或异步启动 capability。

Request:

```json
{
  "workspace": {
    "name": "example-repo",
    "root_uri": "file:///workspace/example-repo",
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
    "safe_rationale": "The inspected route is read-only and does not expose sensitive fields.",
    "confidence": 0.82
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

返回 `run-result.schema.json` shape 的任务结果。不得返回 prompt、trace、skill body、
`skill_text`、`internal` 或 raw runner output。

```json
{
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
