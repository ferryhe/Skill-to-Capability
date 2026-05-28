# MCP Smoke

Use this smoke to verify a local Skill Gateway, the MCP adapter, and a
stdio MCP client configuration without exposing private skills or sensitive
workspace data.

## Scope

This smoke checks that:

- `company-skill-mcp` starts as a stdio MCP server.
- The adapter can reach the configured Gateway.
- The client can see exactly these public MCP tools:
  `list_capabilities`, `run_capability`, `get_task_status`,
  `get_task_result`, and `cancel_task`.
- A non-sensitive sample request can be sent using `examples/sample-workspace`.
- Missing local Hermes or Gateway configuration fails safely without printing
  tokens, prompts, private skill text, or raw runner output.

## Safety Rules

- Use only `examples/sample-workspace/` or another public mock fixture.
- Do not put `.env` files, provider keys, API tokens, customer code, private
  `SKILL.md`, raw traces, raw prompts, skill text, or raw runner stdout/stderr
  in MCP client config, examples, screenshots, logs, or commits.
- Keep committed configs as placeholders. Store real local tokens in your shell,
  OS secret storage, or an untracked local config file with restricted access.
- If a client records prompts/tool transcripts, review them before sharing; they
  must not contain private skill text, provider credentials, or customer data.

## Install And Build

From the repository root:

```bash
npm --prefix mcp-adapter install
npm --prefix mcp-adapter run build
```

For client configs that call `company-skill-mcp` directly, make the local bin
available on your PATH:

```bash
npm --prefix mcp-adapter link
```

If you do not want to link the package, configure the client command as `node`
and pass the absolute path to `mcp-adapter/dist/server.js` before the Gateway
arguments.

## Start Local Gateway

In a separate terminal:

```bash
cd gateway
python -m pip install -e .[dev]
python -m uvicorn gateway.app.main:app --reload --port 8000
```

Check the Gateway health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "gateway"
}
```

## Configure Gateway URL, Token, And Tenant

The adapter requires a Gateway URL. Token and tenant are optional until the G1
auth work lands, but the adapter already accepts them so client configs do not
need to change later.

Environment variables:

```bash
export SKILL_GATEWAY_URL=http://127.0.0.1:8000
export SKILL_GATEWAY_TENANT_ID=local-dev
export SKILL_GATEWAY_TOKEN=replace-with-local-dev-token
```

PowerShell:

```powershell
$env:SKILL_GATEWAY_URL = "http://127.0.0.1:8000"
$env:SKILL_GATEWAY_TENANT_ID = "local-dev"
$env:SKILL_GATEWAY_TOKEN = "replace-with-local-dev-token"
```

CLI flags, which take precedence over environment variables:

```bash
company-skill-mcp --gateway-url http://127.0.0.1:8000 --tenant-id local-dev
```

Supported names:

- URL: `--gateway-url`, `SKILL_GATEWAY_URL`, or `GATEWAY_URL`
- Token: `--gateway-token`, `--token`, `SKILL_GATEWAY_TOKEN`, or `GATEWAY_TOKEN`
- Tenant: `--tenant-id`, `SKILL_GATEWAY_TENANT_ID`, `GATEWAY_TENANT_ID`, or
  `TENANT_ID`

## Client Config Examples

Use the committed templates as safe starting points:

- `examples/mcp/hermes-config.yaml`
- `examples/mcp/cline-config.json`

Both examples register a stdio server named `company-skill-mcp` and use only
placeholder values. The `${SKILL_GATEWAY_TOKEN}` placeholder is expanded only by
some MCP clients. If your client does not expand it, either remove the `env`
entry so `company-skill-mcp` inherits `SKILL_GATEWAY_TOKEN` from the shell, or
put the real token only in an untracked local copy. Do not commit a copy after
replacing placeholders with real local credentials.

## Tool Discovery Smoke

Start or reload your MCP client with the `company-skill-mcp` server enabled.
In the client's MCP tool list, verify these five tools are visible:

```text
list_capabilities
run_capability
get_task_status
get_task_result
cancel_task
```

There must not be a tool that retrieves raw skills, prompts, traces, internal
manifests, or runner output.

Run `list_capabilities`. With the local Gateway running, the response should be
a public capability list that includes `backend-rbac-review`. It must not
include `internal`, `skill_ref`, `model_policy`, prompt text, trace text,
`skill_text`, or private skill body content.

If Gateway is not running, the tool should return a sanitized MCP tool error
such as `Gateway request failed.` with public error metadata only. It should not
print tokens or private local paths.

## Non-Sensitive Run Smoke

Use only public sample context. The following MCP `run_capability` input uses
the committed sample workspace and requests async execution so it does not
require a local Hermes installation. The async smoke below relies on embedded
file content; `root_uri` is still shown as a placeholder. For a real checkout,
use an absolute file URI for your local path, such as
`file:///ABSOLUTE/PATH/TO/Skill-to-Capability/examples/sample-workspace`.

```json
{
  "capability_id": "backend-rbac-review",
  "request": {
    "workspace": {
      "name": "sample-workspace",
      "root_uri": "file:///ABSOLUTE/PATH/TO/Skill-to-Capability/examples/sample-workspace",
      "files": [
        {
          "path": "app.py",
          "content": "class User:\n    def __init__(self, role: str) -> None:\n        self.role = role\n\n\ndef can_view_admin_report(user: User) -> bool:\n    return user.role == \"admin\"\n"
        }
      ]
    },
    "instruction": "Review the sample RBAC helper for public boundary issues.",
    "options": {
      "async": true
    },
    "client": {
      "type": "mcp",
      "version": "0.1.0"
    }
  }
}
```

Expected result:

```json
{
  "task_id": "task_...",
  "status": "queued"
}
```

Then run `get_task_status` with the returned `task_id`. Expected public fields
include `task_id`, `status`, `capability_id`, `created_at`, and `updated_at`.

Run `cancel_task` with the same `task_id`. Expected status is `cancelled`.

Run `get_task_result` with the same `task_id`. Because this smoke cancelled a
queued async task, a safe public error such as `task_cancelled` is expected.

## Optional Real Hermes Smoke

If your machine has Hermes and Gateway runner configuration set up, run the same
sample request without `"async": true`. The Gateway should execute the
server-side Hermes runner and return a completed task result with `task_id`,
`status`, and a nested `result` object containing public report fields such as
`summary`, `findings`, `patch`, `recommended_tests`, `safe_rationale`, and
`confidence`.

If Hermes is missing or misconfigured, the expected failure is a sanitized
Gateway error with code `hermes_runner_error` and HTTP status `502`. That is a
safe local setup failure. It must not include provider credentials, raw runner
stdout/stderr, raw prompts, private `SKILL.md`, or token values.

## Troubleshooting

- `Gateway URL is required`: set `--gateway-url`, `SKILL_GATEWAY_URL`, or
  `GATEWAY_URL` in the MCP client config.
- Tool list is empty: confirm `npm run build` completed and the client command
  can resolve `company-skill-mcp` or the `node dist/server.js` path.
- `Gateway request failed`: confirm the Gateway is running and reachable at the
  configured URL.
- `capability_not_found`: run `list_capabilities` and use one of the returned
  public `id` values.
- `hermes_runner_error`: local Hermes is not installed or not configured for
  the Gateway runner path. Use the async smoke above, or complete local Hermes
  setup before running the real Hermes smoke.
- `invalid_configuration`: check URL syntax and ensure the Gateway URL uses
  `http` or `https`.
