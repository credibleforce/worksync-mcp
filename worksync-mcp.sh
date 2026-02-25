#!/usr/bin/env bash
# WorkSync MCP Server launcher (standalone).
#
# Primary interface: `worksync start` shell function (see ~/.zshrc).
# This script exists for environments without the shell function loaded.
#
# Usage:
#   ./worksync-mcp.sh          # hydrate from 1Password + run in foreground
#   ./worksync-mcp.sh --no-auth  # run without auth (dev mode)

set -euo pipefail

WORKSYNC_DIR="${HOME}/.worksync"
VENV_PYTHON="${WORKSYNC_DIR}/.venv/bin/python"
SERVER_SCRIPT="${WORKSYNC_DIR}/server.py"

if [[ "${1:-}" == "--no-auth" ]]; then
    echo "WorkSync MCP: starting without auth (dev mode)"
    exec "${VENV_PYTHON}" "${SERVER_SCRIPT}"
fi

# Hydrate API key from 1Password
echo "WorkSync MCP: hydrating credentials from 1Password..."

if ! command -v op &>/dev/null; then
    echo "ERROR: 1Password CLI (op) not found." >&2
    exit 1
fi

eval "$(op signin --account my 2>/dev/null)" || true

API_KEY="$(op read 'op://AI/WORKSYNC_API_KEY/credential' 2>/dev/null)" || true

if [[ -z "${API_KEY}" ]]; then
    echo "WARNING: Could not read WORKSYNC_API_KEY. Running without auth." >&2
fi

exec env WORKSYNC_API_KEY="${API_KEY}" "${VENV_PYTHON}" "${SERVER_SCRIPT}"
