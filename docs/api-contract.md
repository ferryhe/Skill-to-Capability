# Skill Gateway API Contract

Base path: `/v1`

## Authentication

`/health` is public. The following endpoints require Gateway API token
authentication:

- `GET /v1/capabilities`
- `GET /v1/capabilities/{id}`
- `POST /v1/capabilities/{id}/run`
- `GET /v1/tasks/{task_id}`
- `GET /v1/tasks/{task_id}/result`
- `POST /v1/tasks/{task_id}/cancel`

Preferred token source:

```http
Authorization: Bearer <token>
```

Gateway local configuration:

- `SKILL_GATEWAY_API_TOKEN_IDENTITIES`: JSON array of token identity records.
  Each record contains `token`, `tenant_id`, and `role` (`viewer` or
  `developer`). In token auth mode, these server-side records are the source of
  tenant/role policy identity. If this variable is present but malformed,
  Gateway fails protected requests closed with `401`.
- `SKILL_GATEWAY_API_TOKENS`: comma-separated allowed API tokens.
- `SKILL_GATEWAY_AUTH_MODE=dev`: explicit local development bypass.
- `SKILL_GATEWAY_AUTH_DISABLED=true`: explicit local development bypass.

Example token identity config:

```json
[
  {
    "token": "dev-only-placeholder-token",
    "tenant_id": "tenant-a",
    "role": "viewer"
  }
]
```

If no allowed tokens are configured and no explicit bypass is set, protected
endpoints fail closed with `401`. Gateway builds a server-side request identity
containing auth mode, a non-reversible token id, tenant id, and role. In token
mode, tenant id and role come from the matched `SKILL_GATEWAY_API_TOKEN_IDENTITIES`
record. Legacy `SKILL_GATEWAY_API_TOKENS` entries without identity metadata use
tenant `default` and role `developer`; request headers cannot escalate them.
Only explicit local dev bypass mode reads `X-Tenant-Id` and `X-User-Role` as
local test identity overrides. Raw tokens are not exposed in responses or errors.

Authentication errors use the public error shape and include
`WWW-Authenticate: Bearer`:

```json
{
  "error": {
    "code": "auth_required",
    "message": "Authentication is required.",
    "details": {}
  }
}
```

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
prompt、trace、skill body、`skill_text` 或 server-only manifest 字段。Gateway 会根据
server-only capability policy 过滤 tenant/role 不可见的 capability。若
`internal.policy.view_roles` 未配置但 `run_roles` 已配置，`run_roles` 同时作为
默认 visibility roles，因此 viewer 不会发现 developer-only capability。

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
prompt、trace、skill body、`skill_text` 或 server-only manifest 字段。若当前 identity
不满足 capability tenant visibility policy，响应与不存在的 capability 相同，返回 `404`。

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
    "expose_skill_text": false,
    "policy": {
      "tenant_allowlist": ["tenant-a"],
      "run_roles": ["developer"]
    }
  }
}
```

## POST /capabilities/{id}/run

同步或异步启动 capability。

Run is allowed only when the authenticated identity can see the capability and
its role is present in server-only `internal.policy.run_roles` when that list is
configured. If `view_roles` is omitted, a role not present in `run_roles` cannot
see or run the capability and receives the same `404 capability_not_found` shape
as a missing capability. A visible capability that denies run permission returns
`403` with code `capability_forbidden`. Omitted policy fields preserve existing
behavior: all authenticated tenants can see the capability and all supported
roles can run it.

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
Tasks are bound to the identity that created them. A different tenant/role/token
identity receives sanitized `404 task_not_found`.

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
Only the task owner identity can read the result; non-owner identities receive
sanitized `404 task_not_found`.

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
Only the task owner identity can cancel queued/running tasks. Non-owner
identities receive sanitized `404 task_not_found`; owner identities still receive
the existing state-specific conflict errors for non-cancellable tasks.

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
