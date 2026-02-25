# WorkSync MCP Server

Shared MCP server for multi-agent work tracking coordination with Obsidian vault synchronization.

## Overview

WorkSync provides a single-writer MCP interface for managing project work tracking (sprints, stories, backlog, history). Multiple AI agents (Claude Code, Codex, etc.) connect to the same server, eliminating filesystem-level concurrency issues.

**Architecture:**
```
Claude Code ──┐
              ├── MCP (HTTP) ──> WorkSync Server (127.0.0.1:8321)
Codex CLI ────┘                    ├── Atomic YAML writes
                                   ├── Debounced vault sync
                                   └── Single-writer consistency
```

## Quick Start

### 1. Install Dependencies

```bash
cd ~/.worksync
uv venv && uv pip install -e .
```

### 2. Set Up Authentication

Create a bearer token in 1Password:

- **Vault:** `AI`
- **Item name:** `WORKSYNC_API_KEY`
- **Field:** `credential`

Add the reference to `~/.claude/.env`:

```bash
WORKSYNC_API_KEY=op://AI/WORKSYNC_API_KEY/credential
```

The `pai()` and `worksync()` shell functions hydrate this from 1Password at startup.
No secrets are written to disk — they only exist in process memory.

### 3. Start the Server

**Recommended — shell function (hydrates from 1Password, runs in background):**
```bash
worksync start     # hydrate from op + start background server
worksync stop      # stop the server
worksync restart   # stop + start
worksync status    # check if running
worksync logs      # tail the log file
```

The `worksync` function is defined in `~/.zshrc`. It signs into 1Password,
reads the API key, and passes it as an env var to the server process.
Secrets only live in memory — never written to disk.

**Standalone script (for environments without the shell function):**
```bash
~/.worksync/worksync-mcp.sh           # hydrate from op + run foreground
~/.worksync/worksync-mcp.sh --no-auth # dev mode, no auth
```

**Manual (dev mode):**
```bash
cd ~/.worksync && .venv/bin/python server.py
```

The server binds to `127.0.0.1:8321` (localhost only).

### 4. Configure Agents

**Claude Code** (in `~/.claude.json` per-project `mcpServers`):

```json
{
  "worksync": {
    "type": "http",
    "url": "http://127.0.0.1:8321/mcp",
    "headers": {
      "Authorization": "Bearer ${WORKSYNC_API_KEY}"
    }
  }
}
```

The `${WORKSYNC_API_KEY}` is expanded from the environment (hydrated by `pai()`).

**Codex** (add to `~/.codex/config.toml`):

```toml
[mcp_servers.worksync]
url = "http://127.0.0.1:8321/mcp"
```

Note: Codex auth headers require a `pai-codex` launcher to hydrate the token
into the environment before starting Codex.

**Codex env layout (recommended):**

Keep non-secret values in `~/.codex/.env` and secrets in `~/.codex/.env.secret`.
Have `pai-codex` read `.env` first, then `.env.secret` so secrets override.
Make sure `WORKSYNC_API_KEY` only lives in `.env.secret` so a `.env` auto-loader
cannot overwrite the hydrated value.

Example `~/.codex/.env.secret`:

```bash
WORKSYNC_API_KEY=op://AI/WORKSYNC_API_KEY/credential
```

### 5. Verify

```bash
cd ~/.worksync && .venv/bin/python test_client.py
```

## Directory Structure

```
~/.worksync/
├── server.py              # MCP server
├── worksync-mcp.sh        # Standalone launcher (hydrates from op)
├── sync.py                # Vault generator (called by server)
├── test_client.py         # Integration test
├── test_parity.py         # Cross-agent parity test
├── pyproject.toml         # Python dependencies
├── config.yaml            # Project registry
├── guidance/              # Foundational coding guidance
│   ├── general.md
│   ├── golang.md
│   ├── typescript.md
│   └── ai-collaboration.md
├── projects/              # Work tracking data (source of truth)
│   └── <project>/
│       ├── work-index.yaml
│       ├── BACKLOG/
│       ├── COMPLETE/
│       ├── PROMPTS/
│       └── SCHEMA/
└── vault/ -> ~/Documents/dev/vault  # Generated Obsidian vault
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `worksync_status` | Show active sprints, in-progress stories, backlog stats |
| `worksync_projects` | List registered projects or get details for one |
| `worksync_add_backlog` | Add a new backlog item |
| `worksync_update_backlog` | Update backlog item fields |
| `worksync_remove_backlog` | Remove a backlog item |
| `worksync_create_sprint` | Create a new sprint |
| `worksync_update_sprint` | Update sprint fields |
| `worksync_add_story` | Add a story to a sprint |
| `worksync_update_story` | Update a story's status or notes |
| `worksync_done` | Mark story done + append history entry |
| `worksync_history` | View or append project history |
| `worksync_sync` | Regenerate Obsidian vault from YAML |
| `worksync_guidance` | Get coding guidance for a project |
| `worksync_register_project` | Register a new project (creates dirs, config, work-index) |
| `worksync_unregister_project` | Remove a project (config + optionally disk + vault) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKSYNC_DATA_ROOT` | `~/.worksync` | Data root directory |
| `WORKSYNC_HOST` | `127.0.0.1` | Server bind address |
| `WORKSYNC_PORT` | `8321` | Server port |
| `WORKSYNC_AUTO_SYNC` | `true` | Auto-sync vault after mutations |
| `WORKSYNC_SYNC_DEBOUNCE` | `2.0` | Seconds to debounce vault sync |
| `WORKSYNC_API_KEY` | _(required)_ | Bearer token for auth. Server refuses to start without it. |
| `WORKSYNC_DEBUG` | `false` | Set to `1` to disable auth (debug/dev only). |

## Security

- **Auth is mandatory**: Server will not start without `WORKSYNC_API_KEY`. Use `WORKSYNC_DEBUG=1` to explicitly disable auth for local development.
- **No secrets on disk**: API key hydrated from 1Password into env var at startup. Never written to a file.
- **Localhost only**: Server binds to `127.0.0.1` — not accessible from the network
- **Bearer token auth**: Every request requires `Authorization: Bearer <token>`
- **1Password integration**: Token stored in vault `AI`, hydrated via `op read` at startup
- **Timing-safe comparison**: Token validation uses `hmac.compare_digest` (constant-time)

**Auth modes:**

| Mode | How | When |
|------|-----|------|
| **Production** | `worksync start` | Normal use — hydrates key from 1Password |
| **Debug** | `WORKSYNC_DEBUG=1 python server.py` | Local dev without 1Password |
| **Missing key** | Server refuses to start | Prevents accidental unauthenticated exposure |

**Auth flow:**
```
worksync start (interactive shell)
  ├── op signin         (biometric/password — interactive)
  ├── op read API_KEY   (from 1Password vault AI)
  ├── WORKSYNC_API_KEY=$key python server.py &  (env var only, no file)
  └── echo $! > .pid    (just the PID, no secrets)
```

## Design Principles

- **Single writer**: All mutations go through the MCP server. Agents read files directly for fast search.
- **Atomic writes**: Uses `mkstemp` + `os.replace` pattern to prevent partial writes.
- **External edit detection**: Tracks file mtimes to detect human edits between MCP calls.
- **Debounced sync**: Rapid mutations collapse into a single vault regeneration (2s default).
- **YAML header preservation**: Maintains `# yaml-language-server` schema comments.
- **Agent attribution**: Each mutation logs which agent made the change (via `agent` tool parameter).

## Obsidian Vault

The vault at `~/.worksync/vault/` (symlinked to `~/Documents/dev/vault`) is generated by `sync.py`. Open it in Obsidian for:

- **Dashboard.md** per project with Dataview queries
- **Graph view** with theme hubs connecting sprints, stories, backlog
- **Tag filtering** by project, type, status, theme
- **Guidance** merged from foundational + project-specific sources

## Development

```bash
# Run tests
cd ~/.worksync && .venv/bin/python test_client.py

# Run parity test (verifies mutations produce consistent state)
cd ~/.worksync && .venv/bin/python test_parity.py

# Start in debug mode (no auth required)
WORKSYNC_DEBUG=1 python server.py
```

## Troubleshooting

### Server won't start: "WORKSYNC_API_KEY is required"

Auth is mandatory. Either:
- Run `worksync start` from a shell with 1Password access (hydrates the key)
- Or for local dev: `WORKSYNC_DEBUG=1 python server.py`

### curl returns 406 Not Acceptable

The MCP endpoint uses JSON-RPC over POST with specific content types. To check auth:

```bash
# Should return 401 (auth enforced) or 200 (valid token)
curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"capabilities":{},"clientInfo":{"name":"test"},"protocolVersion":"2025-03-26"}}' \
  http://127.0.0.1:8321/mcp
```

If you get **406**, the auth middleware isn't active — the server is in debug mode.
If you get **401**, auth is enforced and working.

### Agent gets 401 Unauthorized

The agent's environment doesn't have `WORKSYNC_API_KEY`:
- **Claude**: Ensure `pai` was used to launch (hydrates from `~/.claude/.env`)
- **Codex**: Ensure `pai-codex` was used to launch (hydrates from `~/.codex/.env`)
- Check: `grep Auth ~/.worksync/server.log | tail -1`

### Orphaned vault artifacts after unregister

If `worksync_unregister_project` was called without `delete_data=True`, vault
artifacts may remain. Call it again with `delete_data=True` — it handles
orphaned data (config already removed, disk/vault still present).

### Port 8321 already in use

```bash
# Find what's using it
lsof -i :8321
# Kill and restart
worksync restart
```

### Server log location

```bash
tail -f ~/.worksync/server.log
# or
worksync logs
```
