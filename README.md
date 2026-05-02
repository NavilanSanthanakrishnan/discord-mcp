# Discord User DM MCP

Local MCP server for user-authenticated Discord direct messages.

This project is currently focused on **DMs only**:

- list DM channels
- read recent DM messages
- send a DM message
- keep a singleton Discord Gateway websocket open
- capture incoming DM `MESSAGE_CREATE` events
- poll new DM events through MCP tools
- focus an active watch on one DM conversation

> Important: this project uses a Discord user session token from a local file. Treat that token like a password. Keep it local, never commit it, and understand that automating user accounts can violate Discord's terms of service.

## Current Stack

- Python 3.12+
- MCP Python SDK / FastMCP
- Discord REST API over `httpx`
- Discord Gateway websocket over `websockets`
- SQLite for local DM/event state
- `uv` for development
- `pytest` and `ruff` for tests/linting

The imported Java/Spring Boot baseline is still present as reference code, but the active rebuild lives in:

```text
src/discord_user_mcp/
```

## Local Secrets

The default token path is:

```text
/Users/navilan/Documents/DiscordMCP/token.txt
```

Only the first line is read. This file is ignored by git.

Optional environment variables:

```bash
DISCORD_TOKEN_FILE=/Users/navilan/Documents/DiscordMCP/token.txt
DISCORD_MCP_DB=/Users/navilan/Documents/DiscordMCP/.local/discord_user_mcp.sqlite
DISCORD_API_BASE=https://discord.com/api/v9
DISCORD_GATEWAY_URL='wss://gateway.discord.gg/?v=9&encoding=json'
MCP_HOST=127.0.0.1
MCP_PORT=8085
ALLOW_SEND=true
```

## Run Tests

```bash
uv run ruff check .
uv run pytest
```

## Run The MCP Server

```bash
uv run discord-user-mcp
```

Default MCP endpoint:

```text
http://127.0.0.1:8085/mcp
```

Connect Codex:

```bash
codex mcp add discord-user-dm-mcp --url http://127.0.0.1:8085/mcp
codex mcp list
```

## MCP Tools

### `discord_status`

Returns Gateway/runtime status, including whether the Gateway is connected and how many DMs are cached.

### `list_dms`

Lists DM channels visible to the user session.

Inputs:

```json
{
  "limit": 50,
  "query": "purple",
  "refresh": true
}
```

### `read_dm`

Reads recent messages from a DM channel.

Inputs:

```json
{
  "channel_id": "1486088754560106659",
  "limit": 20,
  "before": null,
  "after": null,
  "around": null
}
```

### `send_dm`

Sends a message to a DM channel. Can be disabled with `ALLOW_SEND=false`.

Inputs:

```json
{
  "channel_id": "1486088754560106659",
  "content": "hello"
}
```

### `poll_new_dm_events`

Returns incoming DM events captured by the Gateway watcher.

Inputs:

```json
{
  "after_event_id": 0,
  "limit": 20,
  "channel_id": null
}
```

### `start_dm_watch`

Focuses incremental polling on a single DM conversation.

Inputs:

```json
{
  "channel_id": "1486088754560106659",
  "context_limit": 30
}
```

### `poll_active_dm`

Returns new incoming events for the active watched DM and advances the active watch cursor.

Inputs:

```json
{
  "wait_seconds": 0,
  "max_events": 10
}
```

### `stop_dm_watch`

Clears the active DM watch.

## Architecture

```text
MCP client
  -> FastMCP HTTP server
    -> DiscordUserMcpRuntime
      -> DiscordRestClient for list/read/send
      -> DiscordGatewayWatcher for live events
      -> SQLite store for DMs/messages/events/watch state
```

The Gateway is singleton. We do **not** open one websocket per DM. The watcher receives global Discord events, filters DM messages, stores them locally, and exposes them through MCP polling tools.

## Verified So Far

- Docker/Java baseline builds successfully.
- Python package lint passes.
- Python unit tests pass.
- REST live test resolved the purplecard DM and sent a clearly marked MCP smoke-test message.
- Gateway live test reached `READY` and cached DM channels.
