# Development

## Install Dev Dependencies

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
cd gateway
python -m pip install -e .[dev]
```

Install JavaScript package dependencies when working on the VSCode extension or
MCP adapter:

```bash
npm --prefix vscode-extension install
npm --prefix mcp-adapter install
```

## Make Targets

The root `Makefile` provides the local H1 acceptance entry points:

```bash
make validate      # schema, fixture, and example capability validation
make syntax        # shell syntax checks for local dev scripts
make test          # contracts, Gateway tests, VSCode tests, and MCP tests
make dev-gateway   # starts the local Gateway dev server
make smoke         # smokes a running Gateway at GATEWAY_URL
```

The Make targets and scripts expect a POSIX shell with `curl`, `mktemp`, and
`tr`. On Windows, run them from Git Bash/MSYS2 or another shell environment that
puts those tools on `PATH`; plain PowerShell usually needs an explicit shell
setup instead of bare `sh`.

If `make` is not available, run the equivalent commands directly:

```bash
python scripts/validate-contracts.py
sh -n scripts/dev-gateway.sh
sh -n scripts/smoke-http.sh
cd gateway && python -m pytest tests -q
npm --prefix vscode-extension test
npm --prefix mcp-adapter test
```

## Local Gateway Dev Server

Start the FastAPI Gateway from the repository root:

```bash
sh scripts/dev-gateway.sh
```

Defaults:

- `GATEWAY_HOST=127.0.0.1`
- `GATEWAY_PORT=8000`
- `GATEWAY_RELOAD=1`
- `SKILL_GATEWAY_AUTH_MODE=dev` only when no auth mode, auth disabled flag, or
  token auth config is already set
- `SKILL_GATEWAY_DEV_RUNNER=mock` only when an explicit dev auth bypass is active
  and no dev runner override is already set

The mock runner override is dev-only and keeps local smoke tests independent of a
Hermes installation. To exercise the manifest's real runner instead, start the
server with an empty override:

```bash
SKILL_GATEWAY_DEV_RUNNER= sh scripts/dev-gateway.sh
```

Do not put tokens in the command line. If you need token auth instead of the
dev bypass, set `SKILL_GATEWAY_AUTH_MODE=token` plus token environment variables
in your shell or secret manager and avoid printing them in logs.

## HTTP Smoke

With the Gateway running in another terminal, run:

```bash
sh scripts/smoke-http.sh
```

The smoke defaults to `http://127.0.0.1:8000` and
`backend-rbac-review`. Override them without changing the script:

```bash
GATEWAY_URL=http://127.0.0.1:8000 CAPABILITY_ID=backend-rbac-review sh scripts/smoke-http.sh
```

The smoke checks:

- `GET /health`
- `GET /v1/capabilities`
- `GET /v1/capabilities/{id}`
- `POST /v1/capabilities/{id}/run` with a non-sensitive mock request

For a non-dev-auth Gateway, set `GATEWAY_TOKEN` or `SKILL_GATEWAY_TOKEN` in the
environment only when the selected capability is already configured to return
the mock result. The default H1 path is the dev-auth/mock-runner Gateway started
by `scripts/dev-gateway.sh`; a token-auth Gateway using the manifest Hermes
runner should use the Hermes smoke flow instead. The script passes tokens through
a temporary curl config file, redacts token values from any diagnostic body
excerpt, and never prints request headers.

## VSCode Extension Dev

Build and test the extension:

```bash
npm --prefix vscode-extension run compile
npm --prefix vscode-extension test
```

For an interactive extension host:

1. Start the Gateway with `sh scripts/dev-gateway.sh`.
2. Open `vscode-extension/` in VSCode.
3. Press `F5` to launch the extension development host.
4. Set `skillCapability.gatewayUrl` to `http://127.0.0.1:8000`.
5. Run `Skill Capability: Refresh Capabilities`.
6. Run a capability from the command palette or the `Skill Capabilities` view
   using non-sensitive workspace context.

When the Gateway is in dev auth mode, no token is needed. For token-auth
testing, keep real tokens in VSCode SecretStorage or local shell secrets, not in
workspace settings JSON.

## MCP Adapter Dev

Build and test the adapter:

```bash
npm --prefix mcp-adapter run build
npm --prefix mcp-adapter test
```

Run the stdio server against the local Gateway:

```bash
GATEWAY_URL=http://127.0.0.1:8000 node mcp-adapter/dist/server.js
```

Use an MCP client to discover the public tools:

```text
list_capabilities
run_capability
get_task_status
get_task_result
cancel_task
```

For local token-auth testing, prefer environment variables over CLI token flags:

```bash
GATEWAY_URL=http://127.0.0.1:8000 GATEWAY_TOKEN=replace-with-local-token node mcp-adapter/dist/server.js
```

The adapter must only expose public Gateway fields. Tool responses must not
include `internal`, `skill_ref`, `model_policy`, prompt text, trace text,
private skill body content, or raw runner output.

## D3 Hermes Runner Smoke

The Hermes smoke runs a real server-side runner path against a non-sensitive
sample workspace. It must not use private skills, customer workspaces, tokens,
credentials, or raw runner output committed to this repository.

```bash
cd gateway
python scripts/smoke_hermes_runner.py --capability backend-rbac-review --sample ../examples/sample-workspace
```

The script prints only the public `CapabilityRunResult` JSON shape to stdout.
If Hermes is missing, misconfigured, returns invalid JSON, or returns unsafe
output, the script prints a safe error message to stderr and exits non-zero.
Because `backend-rbac-review` is configured with the `hermes` runner by default,
the Gateway `POST /v1/capabilities/backend-rbac-review/run` path also requires a
local Hermes CLI/config for synchronous execution. Without Hermes, that endpoint
returns a safe `502` Hermes runner error; tests that need the old mock behavior
must inject or configure the mock runner explicitly.

For tests or local debugging, pass a complete replacement command after
`--command`. Every argument after `--command` belongs to the replacement runner
command, even if it looks like a smoke-script option:

```bash
cd gateway
python scripts/smoke_hermes_runner.py --capability backend-rbac-review --sample ../examples/sample-workspace --command python path/to/fake_runner.py
```

## Safety Rules

- Use only `examples/sample-workspace/` or another non-sensitive local fixture.
- Do not commit real private `SKILL.md` files.
- Do not commit provider keys, tokens, `.env` files, credentials, or customer code.
- Do not print, save, or commit raw runner stdout/stderr, prompts, traces, skill text, or internal manifest fields.
