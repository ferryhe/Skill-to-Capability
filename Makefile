PYTHON ?= python
GATEWAY_URL ?= http://127.0.0.1:8000
POSIX_SH ?= sh

.PHONY: help validate syntax gateway-test vscode-test mcp-test test dev-gateway smoke

help:
	@printf '%s\n' 'Targets:'
	@printf '%s\n' '  make validate      Validate JSON schemas, fixtures, and example capabilities'
	@printf '%s\n' '  make syntax        Check local shell script syntax'
	@printf '%s\n' '  make test          Run contract, Gateway, VSCode extension, and MCP adapter tests'
	@printf '%s\n' '  make dev-gateway   Start the local FastAPI Gateway dev server'
	@printf '%s\n' '  make smoke         Smoke a running Gateway at GATEWAY_URL'

validate:
	$(PYTHON) scripts/validate-contracts.py

syntax:
	$(POSIX_SH) -n scripts/dev-gateway.sh
	$(POSIX_SH) -n scripts/smoke-http.sh

gateway-test:
	cd gateway && $(PYTHON) -m pytest tests -q

vscode-test:
	npm --prefix vscode-extension test

mcp-test:
	npm --prefix mcp-adapter test

test: validate syntax gateway-test vscode-test mcp-test

dev-gateway:
	$(POSIX_SH) scripts/dev-gateway.sh

smoke:
	GATEWAY_URL="$(GATEWAY_URL)" $(POSIX_SH) scripts/smoke-http.sh
