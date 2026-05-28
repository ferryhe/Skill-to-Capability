# Deployment

This document covers local release packaging for the H4 artifacts: Gateway
container image, VSCode VSIX package, and MCP adapter npm tarball.

## Gateway Container

Build the image from the repository root:

```bash
docker build -t skill-gateway:0.1.0 -f gateway/Dockerfile gateway
```

The image contains the Gateway Python package and checked-in public capability
manifests under `gateway/capabilities/`. It does not copy tests, caches,
scripts, `.env` files, or private skill files.

Run with token auth configured explicitly:

```bash
docker run --rm -p 8000:8000 \
  -e SKILL_GATEWAY_AUTH_MODE=token \
  -e SKILL_GATEWAY_API_TOKENS=replace-with-local-token \
  -e 'SKILL_GATEWAY_API_TOKEN_IDENTITIES=[{"token":"replace-with-local-token","tenant_id":"default","role":"developer"}]' \
  skill-gateway:0.1.0
```

Health is public:

```bash
curl http://127.0.0.1:8000/health
```

Capability and task endpoints require auth unless a developer intentionally
starts the Gateway with `SKILL_GATEWAY_AUTH_MODE=dev` or
`SKILL_GATEWAY_AUTH_DISABLED=true`. Do not use those bypasses for production.

For real runner execution, install and configure Hermes in the runtime
environment used by the container, then mount only the non-sensitive workspace
paths the runner needs. Do not bake private skills, customer code, tokens, or
Hermes credentials into the image.

## VSCode VSIX

Package the extension from the repository root:

```bash
npm --prefix vscode-extension install
npm --prefix vscode-extension run package:vsix
```

The package script compiles TypeScript and runs the pinned local
`@vscode/vsce` dev dependency without requiring a global `vsce` install.
`.vscodeignore` excludes source, tests, `node_modules`, local VSIX output, and
development-only metadata while keeping the extension manifest and compiled
`out/` runtime files.

Install the generated VSIX locally:

```bash
code --install-extension vscode-extension/skill-capability-vscode-0.1.0.vsix
```

Configure `skillCapability.gatewayUrl` in VSCode settings. Keep Gateway tokens
in VSCode SecretStorage through the extension flow; do not commit tokens in
workspace settings JSON.

## MCP Adapter npm Package

Create the local package:

```bash
npm --prefix mcp-adapter install
npm --prefix mcp-adapter run pack:local
```

Install the tarball into an MCP client project:

```bash
npm install /path/to/skill-capability-mcp-adapter-0.1.0.tgz
```

Local stdio configuration example:

```json
{
  "mcpServers": {
    "skill-gateway": {
      "command": "company-skill-mcp",
      "env": {
        "GATEWAY_URL": "http://127.0.0.1:8000",
        "GATEWAY_TOKEN": "replace-with-local-token",
        "GATEWAY_TENANT_ID": "default"
      }
    }
  }
}
```

The adapter exposes five public tools:

- `list_capabilities`
- `run_capability`
- `get_task_status`
- `get_task_result`
- `cancel_task`

The tarball is a local-install skeleton, not a registry publishing workflow.
Do not publish it to an external npm registry until package ownership, naming,
license, provenance, and secret-scanning gates are defined.

## Security Notes

- Default production posture is token auth; missing token configuration should
  fail closed for protected endpoints.
- Tenant and role identity come from server-side token configuration, not
  trusted client headers.
- Store tokens in environment variables or a secret manager. Avoid CLI token
  flags except for short-lived local tests because shell history may persist.
- Never package private skill text, prompts, raw runner output, traces,
  customer workspace contents, `.env` files, PEM/key material, or credentials.
- The VSCode extension and MCP adapter are thin clients. They must receive only
  public capability fields and filtered run results from the Gateway.
