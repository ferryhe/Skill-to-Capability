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

MVP 支持：

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
- patch preview button
- recommended tests
- task metadata

不得显示：

- internal manifest
- prompt
- skill body
- raw trace

## Testing targets

- API client maps Gateway errors correctly。
- context collector respects denylist and byte limits。
- patch apply rejects workspace escape。
- UI renderer ignores internal fields even if server accidentally returns them。
