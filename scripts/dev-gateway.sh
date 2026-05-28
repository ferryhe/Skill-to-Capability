#!/usr/bin/env sh
set -eu

fail() {
  printf 'dev-gateway: %s\n' "$1" >&2
  exit 1
}

case $0 in
  */*) SCRIPT_PARENT=${0%/*} ;;
  *) SCRIPT_PARENT=. ;;
esac
SCRIPT_DIR=$(CDPATH= cd "$SCRIPT_PARENT" && pwd)
REPO_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON:-python}
GATEWAY_HOST=${GATEWAY_HOST:-127.0.0.1}
GATEWAY_PORT=${GATEWAY_PORT:-8000}
GATEWAY_RELOAD=${GATEWAY_RELOAD:-1}
SMOKE_SHELL=${POSIX_SH:-sh}

if [ "${SKILL_GATEWAY_AUTH_MODE+x}" = "" ] \
  && [ "${SKILL_GATEWAY_AUTH_DISABLED+x}" = "" ] \
  && [ "${SKILL_GATEWAY_API_TOKENS+x}" = "" ] \
  && [ "${SKILL_GATEWAY_API_TOKEN_IDENTITIES+x}" = "" ]; then
  SKILL_GATEWAY_AUTH_MODE=dev
  export SKILL_GATEWAY_AUTH_MODE
fi

DEV_AUTH_BYPASS=0
case "${SKILL_GATEWAY_AUTH_MODE:-}" in
  [Dd][Ee][Vv]) DEV_AUTH_BYPASS=1 ;;
esac
case "${SKILL_GATEWAY_AUTH_DISABLED:-}" in
  [Tt][Rr][Uu][Ee]) DEV_AUTH_BYPASS=1 ;;
esac

if [ "${SKILL_GATEWAY_DEV_RUNNER+x}" = "" ] && [ "$DEV_AUTH_BYPASS" = "1" ]; then
  SKILL_GATEWAY_DEV_RUNNER=mock
  export SKILL_GATEWAY_DEV_RUNNER
fi

[ -d "$REPO_ROOT/gateway/gateway" ] || fail "run from this repository checkout; gateway package was not found."
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "python executable not found: $PYTHON_BIN"

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  fail "Gateway dependencies are missing. Run: python -m pip install -r requirements-dev.txt && cd gateway && python -m pip install -e .[dev]"
fi

printf 'Starting Skill Gateway dev server on http://%s:%s\n' "$GATEWAY_HOST" "$GATEWAY_PORT"
printf '  auth mode: %s\n' "${SKILL_GATEWAY_AUTH_MODE:-token}"
if [ -n "${SKILL_GATEWAY_DEV_RUNNER:-}" ]; then
  printf '  dev runner override: %s\n' "$SKILL_GATEWAY_DEV_RUNNER"
else
  printf '  dev runner override: disabled; using manifest runner\n'
fi
printf '  smoke command: GATEWAY_URL=http://%s:%s %s scripts/smoke-http.sh\n' "$GATEWAY_HOST" "$GATEWAY_PORT" "$SMOKE_SHELL"

cd "$REPO_ROOT/gateway"
if [ "$GATEWAY_RELOAD" = "0" ]; then
  exec "$PYTHON_BIN" -m uvicorn gateway.app.main:app --host "$GATEWAY_HOST" --port "$GATEWAY_PORT" "$@"
fi

exec "$PYTHON_BIN" -m uvicorn gateway.app.main:app --host "$GATEWAY_HOST" --port "$GATEWAY_PORT" --reload "$@"
