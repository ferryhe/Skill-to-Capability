#!/usr/bin/env sh
set -eu

fail() {
  printf 'smoke-http: %s\n' "$1" >&2
  exit 1
}

case $0 in
  */*) SCRIPT_PARENT=${0%/*} ;;
  *) SCRIPT_PARENT=. ;;
esac
SCRIPT_DIR=$(CDPATH= cd "$SCRIPT_PARENT" && pwd)
REPO_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON:-python}
GATEWAY_URL=${1:-${GATEWAY_URL:-http://127.0.0.1:8000}}
GATEWAY_URL=${GATEWAY_URL%/}
CAPABILITY_ID=${CAPABILITY_ID:-backend-rbac-review}
TOKEN=${GATEWAY_TOKEN:-${SKILL_GATEWAY_TOKEN:-${SKILL_GATEWAY_API_TOKEN:-}}}
TENANT_ID=${GATEWAY_TENANT_ID:-${SKILL_GATEWAY_TENANT_ID:-}}
TMPDIR=${TMPDIR:-/tmp}

[ -d "$REPO_ROOT" ] || fail "repository root was not found."
command -v curl >/dev/null 2>&1 || fail "curl is required for HTTP smoke."
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "python executable not found: $PYTHON_BIN"
command -v mktemp >/dev/null 2>&1 || fail "mktemp is required for temporary smoke files."
command -v tr >/dev/null 2>&1 || fail "tr is required for token safety checks."

BODY_FILE=$(mktemp "$TMPDIR/skillgw-smoke-body.XXXXXX") || fail "could not create temp response file."
PAYLOAD_FILE=$(mktemp "$TMPDIR/skillgw-smoke-payload.XXXXXX") || fail "could not create temp payload file."
CURL_CONFIG=$(mktemp "$TMPDIR/skillgw-smoke-curl.XXXXXX") || fail "could not create temp curl config."

cleanup() {
  rm -f "$BODY_FILE" "$PAYLOAD_FILE" "$CURL_CONFIG"
}
trap cleanup EXIT HUP INT TERM

case "$TOKEN" in
  *\"*) fail "GATEWAY_TOKEN/SKILL_GATEWAY_TOKEN must not contain double quotes." ;;
esac
case "$TENANT_ID" in
  *\"*) fail "GATEWAY_TENANT_ID/SKILL_GATEWAY_TENANT_ID must not contain double quotes." ;;
esac
TOKEN_ONELINE=$(printf '%s' "$TOKEN" | tr -d '\r\n')
TENANT_ONELINE=$(printf '%s' "$TENANT_ID" | tr -d '\r\n')
[ "$TOKEN" = "$TOKEN_ONELINE" ] || fail "GATEWAY_TOKEN/SKILL_GATEWAY_TOKEN must be a single line."
[ "$TENANT_ID" = "$TENANT_ONELINE" ] || fail "GATEWAY_TENANT_ID/SKILL_GATEWAY_TENANT_ID must be a single line."

{
  printf '%s\n' 'silent'
  printf '%s\n' 'show-error'
  printf '%s\n' 'header = "Accept: application/json"'
  printf '%s\n' 'header = "Content-Type: application/json"'
  if [ -n "$TOKEN" ]; then
    printf 'header = "Authorization: Bearer %s"\n' "$TOKEN"
  fi
  if [ -n "$TENANT_ID" ]; then
    printf 'header = "X-Tenant-Id: %s"\n' "$TENANT_ID"
  fi
} >"$CURL_CONFIG"
chmod 600 "$CURL_CONFIG" 2>/dev/null || true

print_response_excerpt() {
  "$PYTHON_BIN" - "$BODY_FILE" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")
for token_name in ("GATEWAY_TOKEN", "SKILL_GATEWAY_TOKEN", "SKILL_GATEWAY_API_TOKEN"):
    token = os.environ.get(token_name)
    if token:
        text = text.replace(token, "[redacted-token]")
try:
    data = json.loads(text)
except json.JSONDecodeError:
    print(text[:2000], file=sys.stderr)
    sys.exit(0)
error = data.get("error") if isinstance(data, dict) else None
if isinstance(error, dict) and error.get("code") == "hermes_runner_error":
    print(
        "Hint: the Gateway is using the Hermes runner. Start it with "
        "`sh scripts/dev-gateway.sh`, or launch with both "
        "SKILL_GATEWAY_AUTH_MODE=dev and SKILL_GATEWAY_DEV_RUNNER=mock.",
        file=sys.stderr,
    )
print(json.dumps(data, indent=2)[:2000], file=sys.stderr)
PY
}

assert_no_server_only_fields() {
  label=$1
  "$PYTHON_BIN" - "$BODY_FILE" "$label" <<'PY'
import json
import re
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
label = sys.argv[2]
forbidden_keys = {
    "internal",
    "internal_state",
    "model_policy",
    "model_provider",
    "provider",
    "provider_info",
    "skill_ref",
    "skill_body",
    "skill_text",
    "system_prompt",
    "developer_prompt",
    "full_prompt",
    "raw_prompt",
    "prompt",
    "prompt_text",
    "trace",
    "tool_trace",
    "raw_runner_output",
    "chain_of_thought",
}
forbidden_normalized = {
    re.sub(r"[^a-z0-9]+", "", key.casefold()) for key in forbidden_keys
}


def normalized_key(key):
    return re.sub(r"[^a-z0-9]+", "", str(key).casefold())


def walk(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            if normalized_key(key) in forbidden_normalized:
                raise SystemExit(f"{label} leaked server-only field: {path}.{key}")
            walk(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            walk(item, f"{path}[{index}]")


walk(data)
PY
}

request() {
  method=$1
  path=$2
  expected_status=$3
  data_file=${4:-}
  url=$GATEWAY_URL$path

  if [ -n "$data_file" ]; then
    if ! http_status=$(curl --config "$CURL_CONFIG" -X "$method" --data-binary "@$data_file" -o "$BODY_FILE" -w "%{http_code}" "$url"); then
      fail "could not reach $url"
    fi
  else
    if ! http_status=$(curl --config "$CURL_CONFIG" -X "$method" -o "$BODY_FILE" -w "%{http_code}" "$url"); then
      fail "could not reach $url"
    fi
  fi

  if [ "$http_status" != "$expected_status" ]; then
    printf 'smoke-http: %s %s returned HTTP %s; expected %s\n' "$method" "$path" "$http_status" "$expected_status" >&2
    print_response_excerpt
    exit 1
  fi
}

assert_health() {
  "$PYTHON_BIN" - "$BODY_FILE" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data != {"status": "ok", "service": "gateway"}:
    raise SystemExit(f"health response mismatch: {data!r}")
PY
}

assert_capability_list() {
  "$PYTHON_BIN" - "$BODY_FILE" "$CAPABILITY_ID" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
capability_id = sys.argv[2]
capabilities = data.get("capabilities")
if not isinstance(capabilities, list):
    raise SystemExit("capability list response missing capabilities array")
if capability_id not in {capability.get("id") for capability in capabilities if isinstance(capability, dict)}:
    raise SystemExit(f"capability list did not include {capability_id!r}")
PY
  assert_no_server_only_fields "capability list"
}

assert_capability_detail() {
  "$PYTHON_BIN" - "$BODY_FILE" "$CAPABILITY_ID" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
capability_id = sys.argv[2]
if data.get("id") != capability_id:
    raise SystemExit(f"capability detail id mismatch: {data.get('id')!r}")
PY
  assert_no_server_only_fields "capability detail"
}

assert_mock_run() {
  "$PYTHON_BIN" - "$BODY_FILE" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if data.get("status") != "completed":
    raise SystemExit(f"mock run did not complete synchronously: {data!r}")
result = data.get("result")
if not isinstance(result, dict):
    raise SystemExit("mock run response missing result object")
summary = result.get("summary", "")
safe_rationale = result.get("safe_rationale", "")
if "Mock review completed" not in summary or "mock runner" not in safe_rationale:
    raise SystemExit("run response was not produced by the mock runner")
if not isinstance(result.get("recommended_tests"), list):
    raise SystemExit("mock run response missing recommended_tests array")
PY
  assert_no_server_only_fields "run response"
}

cat >"$PAYLOAD_FILE" <<'JSON'
{
  "workspace": {
    "name": "local-smoke",
    "root_uri": "file:///local-smoke",
    "git_branch": "local-dev",
    "git_diff": "diff --git a/app.py b/app.py\n",
    "files": [
      {
        "path": "app.py",
        "content": "def hello():\n    return 'world'\n"
      }
    ]
  },
  "instruction": "Run the local mock smoke with non-sensitive sample context.",
  "options": {
    "return_patch": false
  },
  "client": {
    "type": "cli",
    "version": "local-smoke"
  }
}
JSON

printf 'Smoke Gateway at %s\n' "$GATEWAY_URL"

request GET /health 200
assert_health
printf '  ok: health\n'

request GET /v1/capabilities 200
assert_capability_list
printf '  ok: capability list\n'

request GET "/v1/capabilities/$CAPABILITY_ID" 200
assert_capability_detail
printf '  ok: capability detail\n'

request POST "/v1/capabilities/$CAPABILITY_ID/run" 200 "$PAYLOAD_FILE"
assert_mock_run
printf '  ok: mock capability run\n'

printf 'Smoke passed without printing tokens or private capability fields.\n'
