# Sample Workspace

This is a non-sensitive H2 end-to-end fixture. It intentionally contains a small
mock RBAC bug in `app.py`: any active user can view the admin report, even when
the user is not an admin.

The baseline test should fail:

```bash
python -m unittest discover -s tests -v
```

After applying `patches/fix-rbac.patch`, the same test command should pass.

Safety rules:

- Do not add real private skills, prompts, tokens, credentials, customer code,
  or raw runner output here.
- Generated Gateway smoke output belongs in `.skillgw/`, which is ignored.
- The fake Hermes runner at `../../scripts/h2_fake_hermes_runner.py` returns
  only the public run-result JSON shape and does not execute arbitrary workspace
  code.
