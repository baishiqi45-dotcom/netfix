.PHONY: help lint test smoke api-smoke mcp-smoke app case clean

help:
	@echo "netfix local dev targets"
	@echo "  make lint       - syntax-check Python and shell scripts"
	@echo "  make test       - run unit tests"
	@echo "  make smoke      - run CLI smoke tests"
	@echo "  make api-smoke  - start API server and check /health + /"
	@echo "  make mcp-smoke  - run MCP server smoke test"
	@echo "  make app        - build SwiftUI menu bar app"
	@echo "  make app-bundle - build Netfix.app bundle"
	@echo "  make case       - capture a fresh healthy/codex case"
	@echo "  make clean      - remove generated artifacts"

lint:
	python3 -m py_compile netfix/*.py
	bash -n bin/*.sh

test:
	python3 -m unittest discover tests -v

smoke:
	python3 netfix.py --help >/dev/null
	python3 netfix.py triage --json --timeout 8 >/dev/null

api-smoke:
	@python3 netfix.py server --host 127.0.0.1 --port 8766 --timeout 10 & \
	SERVER_PID=$$!; \
	sleep 2; \
	curl -fs http://127.0.0.1:8766/health >/dev/null && echo "API /health OK"; \
	curl -fs http://127.0.0.1:8766/ >/dev/null && echo "Web dashboard OK"; \
	kill $$SERVER_PID 2>/dev/null || true

mcp-smoke:
	@echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}' | python3 -m netfix.mcp_server >/dev/null && echo "MCP OK"

app:
	cd gui/macos && swift build

app-bundle:
	cd gui/macos && ./build_app.sh --install

case:
	python3 netfix.py codex --json --timeout 10 --save-case

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	cd gui/macos && swift package clean 2>/dev/null || true
	rm -rf gui/macos/.build/Netfix.app 2>/dev/null || true
