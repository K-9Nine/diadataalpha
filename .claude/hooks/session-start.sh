#!/bin/bash
# SessionStart hook: install Python deps so tests/linting and `run` work
# immediately in Claude Code on the web sessions. Idempotent + non-interactive.
set -euo pipefail

# Only needed in the remote (web) environment; local devs manage their own venv.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# uv is preinstalled in the web environment. Create the venv if absent, then
# install the package with dev extras (pytest). `uv pip install -e` is cheap to
# re-run, so this is safe on resume/clear/compact.
uv venv --python 3.11 >/dev/null 2>&1 || true
uv pip install -e '.[dev]'

# Make the venv the default interpreter for subsequent commands this session.
echo "export VIRTUAL_ENV=\"${CLAUDE_PROJECT_DIR:-.}/.venv\"" >> "$CLAUDE_ENV_FILE"
echo "export PATH=\"${CLAUDE_PROJECT_DIR:-.}/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
