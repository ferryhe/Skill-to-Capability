# H2 End-to-End Smoke

This smoke verifies the H2 sample workspace loop without private skills,
tokens, customer code, Docker, CI, or VSIX packaging.

## Scope

The smoke covers:

- `examples/sample-workspace/` starts with a clear mock RBAC bug.
- The baseline sample test fails before a patch is applied.
- The H1 dev Gateway mock runner can return a public run-result with a patch.
- The fake Hermes runner command can return the same public patch shape through
  `gateway/scripts/smoke_hermes_runner.py`.
- VSCode can preview/apply the patch manually, or `git apply` can be used as a
  command-line equivalent.
- The sample tests pass after the patch is applied.

## Safety Rules

- Use only `examples/sample-workspace/` or a temporary copy of it.
- Do not add real private `SKILL.md`, prompts, provider keys, API tokens,
  credentials, customer code, or raw runner output to this repository.
- Generated smoke output belongs under `examples/sample-workspace/.skillgw/`,
  which is ignored.
- The fake Hermes runner under `scripts/h2_fake_hermes_runner.py` is
  deterministic sample code. It is not a private Hermes integration and does
  not execute workspace code.

## 1. Install Local Dependencies

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
cd gateway
python -m pip install -e .[dev]
cd ..
npm --prefix vscode-extension install
```

If dependencies are already installed, this step can be skipped.

## 2. Confirm The Sample Bug

Run the sample tests from the sample workspace:

```bash
cd examples/sample-workspace
python -m unittest discover -s tests -v
```

Expected result before applying the patch: one failure in
`test_active_non_admin_cannot_view_admin_report`. That failure proves the sample
RBAC bug is present.

Return to the repository root before continuing:

```bash
cd ../..
```

## 3. Start The H1 Dev Gateway

In a separate terminal from the repository root:

```bash
sh scripts/dev-gateway.sh
```

The script enables `SKILL_GATEWAY_AUTH_MODE=dev` and
`SKILL_GATEWAY_DEV_RUNNER=mock` when no auth config is already set. That local
dev mock runner is what returns the deterministic sample patch without calling
real Hermes.

Check the Gateway:

```bash
sh scripts/smoke-http.sh
```

## 4. Request The Patch From Gateway

With the dev Gateway running, request the H2 sample patch:

```bash
python scripts/h2_request_gateway_patch.py \
  --gateway-url http://127.0.0.1:8000 \
  --out-dir examples/sample-workspace/.skillgw
```

Expected output includes:

- `"status": "completed"`
- `examples/sample-workspace/.skillgw/run-result.json`
- `examples/sample-workspace/.skillgw/fix-rbac.patch`

The saved JSON and patch must not contain `internal`, `skill_ref`,
`model_policy`, prompt text, trace text, private skill body content, tokens, or
raw runner output.

## 5. Optional Fake Hermes Patch Smoke

This command exercises the Hermes runner contract with a safe fake command. It
does not require a real Hermes install:

```bash
python gateway/scripts/smoke_hermes_runner.py \
  --capability backend-rbac-review \
  --sample examples/sample-workspace \
  --command python scripts/h2_fake_hermes_runner.py
```

Expected result: public `CapabilityRunResult` JSON on stdout with a non-null
`patch` and `recommended_tests` set to:

```text
python -m unittest discover -s tests -v
```

## 6. Apply Patch In VSCode

Manual VSCode path:

1. Start the Gateway with `sh scripts/dev-gateway.sh`.
2. Open `examples/sample-workspace/` in VSCode.
3. In the extension development host, configure
   `skillCapability.gatewayUrl` as `http://127.0.0.1:8000`.
4. Run `Skill Capability: Refresh Capabilities`.
5. Open `app.py` and run `Skill Capability: Run Current File` for
   `Backend RBAC Review`.
6. Review the report and patch preview.
7. Run `Skill Capability: Apply Last Patch` and confirm the apply prompt.
8. Run `Skill Capability: Run Recommended Tests` and confirm the test command,
   or run the test command manually.

This VSCode flow is intentionally manual because E5/E6 require user
confirmation before writing files or running commands.

Command-line equivalent when you are not using the VSCode extension host:

```bash
cd examples/sample-workspace
git apply .skillgw/fix-rbac.patch
python -m unittest discover -s tests -v
```

Expected result after applying the patch: all three sample tests pass.

To reset the sample workspace after a local smoke, reverse only the sample patch:

```bash
git apply -R .skillgw/fix-rbac.patch
```

Do not use broad reset commands if other workers have unrelated changes in the
repository.

## 7. Verification Commands

Run the focused H2 checks:

```bash
python -m pytest gateway/tests/test_run_capability.py -q -k sample_rbac_patch
python gateway/scripts/smoke_hermes_runner.py --capability backend-rbac-review --sample examples/sample-workspace --command python scripts/h2_fake_hermes_runner.py
python scripts/validate-contracts.py
git diff --check
```

For the sample workspace, verify in a temporary copy so the committed fixture
remains intentionally vulnerable:

```bash
tmpdir=$(mktemp -d)
cp -R examples/sample-workspace "$tmpdir/sample-workspace"
cd "$tmpdir/sample-workspace"
if python -m unittest discover -s tests -v; then
  echo "baseline sample tests unexpectedly passed"
  exit 1
fi
git apply patches/fix-rbac.patch
python -m unittest discover -s tests -v
```
