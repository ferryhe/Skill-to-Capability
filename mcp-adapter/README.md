# Skill Capability MCP Adapter

MCP stdio adapter for the Skill Gateway. It lets local MCP clients call approved
Gateway capabilities without packaging private skill text, prompts, traces, or
server-only manifest fields.

## Package Locally

Build and create a local npm tarball:

```bash
npm install
npm run build
npm pack
```

The tarball contains the runtime JavaScript files, this README, and
`package.json`. It excludes `src/`, `dist/test/`, `node_modules/`, and test
sources.

Install it into another local project:

```bash
npm install /path/to/skill-capability-mcp-adapter-0.1.0.tgz
```

Or run it directly from this workspace after building:

```bash
node dist/server.js --gateway-url http://127.0.0.1:8000
```

## Configuration

Required:

- `GATEWAY_URL` or `--gateway-url`: base URL for the Skill Gateway.

Optional:

- `GATEWAY_TOKEN` or `SKILL_GATEWAY_TOKEN`: bearer token for token-auth Gateway
  deployments.
- `GATEWAY_TENANT_ID` or `--tenant-id`: tenant identity to send to the Gateway.
- `--gateway-token`: local-only token flag. Prefer environment variables or a
  client secret store so tokens do not appear in shell history.

Example:

```bash
GATEWAY_URL=http://127.0.0.1:8000 \
GATEWAY_TOKEN=replace-with-local-token \
company-skill-mcp
```

## Tools

The adapter exposes exactly five public tools:

- `list_capabilities`
- `run_capability`
- `get_task_status`
- `get_task_result`
- `cancel_task`

`run_capability` sends the nested `request` object to the Gateway
`/v1/capabilities/{id}/run` endpoint. Responses are recursively stripped of
server-only fields before they are returned to the MCP client.

## Safety

Do not package or configure private `SKILL.md` files in this adapter. Keep
tokens out of committed config files and logs. The Gateway is responsible for
tenant auth, capability policy, audit logging, private runner execution, and
output filtering; this adapter is only a thin public transport layer.
