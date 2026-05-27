# Development

## Install Dev Dependencies

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
cd gateway
python -m pip install -e .[dev]
```

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
