# VSCode Extension Contract

## 目标

让用户在 VSCode 中像使用产品功能一样调用私有 skill 包装出来的 capability，并能安全修改 workspace。

## 用户流程

```text
Open workspace
  -> Company AI: Run Capability
  -> choose capability
  -> choose context: current file / selected files / git diff
  -> enter instruction
  -> run
  -> view report/findings
  -> preview patch
  -> apply patch after approval
  -> optionally run recommended tests
```

## Commands

MVP commands:

- `skillCapability.configureGateway`
- `skillCapability.refreshCapabilities`
- `skillCapability.runCapability`
- `skillCapability.runCurrentFile`
- `skillCapability.runCurrentGitDiff`
- `skillCapability.applyLastPatch`
- `skillCapability.runRecommendedTests`

## Settings

```json
{
  "skillCapability.gatewayUrl": "https://gateway.example.com",
  "skillCapability.tenantId": "default",
  "skillCapability.confirmLargeUploads": true,
  "skillCapability.maxFiles": 20,
  "skillCapability.maxTotalBytes": 300000
}
```

Token 不应存在普通 settings JSON；优先使用 VSCode secret storage。

## Context Collector

MVP 支持的 context 必须映射到 `run-request.schema.json`：

- current file
- selected files from explorer
- active editor selection
- current git diff
- workspace metadata: repo name, branch

默认拒绝：

- `.env`
- `*.pem`
- `*.key`
- `id_rsa`
- `credentials.json`
- binary files
- files over configured size

Gateway request body example:

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
    "type": "vscode",
    "version": "0.1.0"
  }
}
```

## Patch Apply

推荐默认体验：

```text
Analyze -> Preview Diff -> Apply -> Optional Test
```

Extension 必须在 apply 前验证：

- patch path 在 workspace 内。
- patch 不写 denylisted files。
- patch 对应文件未发生不可合并变化，或要求用户处理冲突。

## Report UI

Report webview 显示：

- summary
- findings by severity/path
- safe_rationale
- confidence when present
- patch preview button
- recommended tests
- artifacts public metadata
- task metadata from task endpoints

不得显示：

- internal manifest
- prompt
- skill body or `skill_text`
- raw trace

Expected run result shape:

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

## Testing targets

- API client maps Gateway errors correctly。
- context collector respects denylist and byte limits。
- patch apply rejects workspace escape。
- UI renderer treats any `internal`, `prompt`, `trace`, or `skill_text` field as a protocol violation and does not render it。
