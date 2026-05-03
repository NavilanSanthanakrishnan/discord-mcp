# Discord MCP

Local MCP server for Discord automation through MCP tools.

The recommended production-friendly setup is to use an official Discord bot token with
the permissions and intents your application needs. For local research and personal
experimentation, the same transport can technically be pointed at a Discord user-session
Authorization token, but that mode should be treated as private, experimental, and subject
to Discord's terms and API behavior. Not every tool is available in every auth mode:
bot-token workflows are best for server/guild automation, while some client-account
features require a user-session context.

This project currently supports:

- list DM channels when the auth mode supports them
- read recent messages
- send messages
- reply to a specific message
- edit/delete messages the authenticated actor owns or can manage
- add/remove reactions
- send local file attachments
- send typing indicators and natural typed messages
- keep a singleton Discord Gateway websocket open
- capture incoming DM `MESSAGE_CREATE` and `TYPING_START` events
- poll new DM events through MCP tools
- collect a natural DM burst after the sender pauses
- focus an active watch on one DM conversation with an idle timeout
- list servers/guilds
- list server text-like channels
- read/send/reply/react in server channels

> Safety note: use a Discord bot token for public, shared, or production deployments.
> If you choose to experiment locally with a user-session Authorization token, treat it
> like a password, keep it private, never commit it, and understand that automating user
> accounts may violate Discord's terms of service.

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

## Authentication

The MCP server reads one line from `DISCORD_TOKEN_FILE` and passes it as the
Discord `Authorization` header.

Recommended bot-token format:

```text
Bot YOUR_DISCORD_BOT_TOKEN
```

Optional local experimental user-session format:

```text
YOUR_DISCORD_USER_SESSION_TOKEN
```

The default token path is:

```text
./token.txt
```

Only the first line is read. This file is ignored by git. Because different auth modes
have different Discord API permissions, some tools may fail if the current token type
does not have access to that endpoint.

Optional environment variables:

```bash
DISCORD_TOKEN_FILE=./token.txt
DISCORD_MCP_DB=./.local/discord_user_mcp.sqlite
DISCORD_API_BASE=https://discord.com/api/v9
DISCORD_GATEWAY_URL='wss://gateway.discord.gg/?v=9&encoding=json'
MCP_HOST=127.0.0.1
MCP_PORT=8085
ALLOW_SEND=true
NATURAL_TYPING_WPM=55
NATURAL_TYPING_MIN_SECONDS=1.0
NATURAL_TYPING_MAX_SECONDS=20.0
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
codex mcp add discord-mcp --url http://127.0.0.1:8085/mcp
codex mcp list
```

## MCP Tools

### `discord_status`

Returns Gateway/runtime status, including whether the Gateway is connected and how many DMs are cached.

### `get_custom_status`

Reads the authenticated session's current presence status and custom status.

Output:

```json
{
  "status": "dnd",
  "custom_status": {
    "text": "working",
    "expires_at": null,
    "emoji_id": null,
    "emoji_name": null
  }
}
```

### `set_custom_status`

Sets or clears the authenticated session's custom status. This uses Discord's JSON settings endpoint, not the protobuf settings endpoint.

Inputs:

```json
{
  "text": "working",
  "emoji_name": "🔥",
  "emoji_id": null,
  "expires_at": null
}
```

Supported patterns:

```text
Text only: text="working"
Unicode emoji: emoji_name="🔥"
Custom emoji: emoji_name="emoji_name", emoji_id="CUSTOM_OR_DISCORD_ID"
Expiration: expires_at="2026-05-03T00:00:00.000Z"
Clear custom status: omit all fields or pass nulls
```

### `list_dms`

Lists DM channels visible to the current auth context, when supported.

Inputs:

```json
{
  "limit": 50,
  "query": "example",
  "refresh": true
}
```

### `list_servers`

Lists Discord servers/guilds visible to the current auth context.

Inputs:

```json
{
  "limit": 100,
  "query": "server name"
}
```

### `list_server_channels`

Lists text-like channels for a server/guild.

Inputs:

```json
{
  "guild_id": "CUSTOM_OR_DISCORD_ID",
  "limit": 100,
  "query": "general"
}
```

### `read_messages`

Reads recent messages from a DM or server channel. By default this returns compact, token-efficient rows.

Inputs:

```json
{
  "channel_id": "CUSTOM_OR_DISCORD_ID",
  "limit": 20,
  "before": null,
  "after": null,
  "around": null,
  "compact": true
}
```

Compact output:

```json
[
  {
    "message_id": "CUSTOM_OR_DISCORD_ID",
    "person": "examplefriend",
    "user_id": "USER_ID",
    "message": "yo can you check this?",
    "time": "2026-05-02T01:45:19.152000+00:00"
  }
]
```

Set `compact=false` only when the agent needs attachments, edit timestamps, or reply references.

### `send_message`

Sends a normal message to a DM or server channel. Can be disabled with `ALLOW_SEND=false`.

For server pings, include normal Discord mention syntax in `content`.

```json
{
  "channel_id": "CUSTOM_OR_DISCORD_ID",
  "content": "hello <@CUSTOM_OR_DISCORD_ID>"
}
```

Mention forms:

```text
User: <@USER_ID>
Role: <@&ROLE_ID>
Channel: <#CHANNEL_ID>
Everyone/here: @everyone or @here, if Discord allows the authenticated actor to use them
```

### `send_natural_message`

Sends typing indicators for a human-ish duration based on message length and WPM, then sends the message to a DM or server channel.

Inputs:

```json
{
  "channel_id": "CUSTOM_OR_DISCORD_ID",
  "content": "hello, this is typed naturally",
  "wpm": 55,
  "min_seconds": 1.0,
  "max_seconds": 20.0
}
```

If the optional timing fields are omitted, the server uses `NATURAL_TYPING_WPM`, `NATURAL_TYPING_MIN_SECONDS`, and `NATURAL_TYPING_MAX_SECONDS`.

### `reply_to_message`

Replies to one specific message in a DM or server channel. Internally, this sends a normal Discord message with a `message_reference`.

Inputs:

```json
{
  "channel_id": "CUSTOM_OR_DISCORD_ID",
  "message_id": "CUSTOM_OR_DISCORD_ID",
  "content": "replying directly to that message"
}
```

Typical flow:

```text
read_messages -> pick message_id -> reply_to_message
```

### `send_typing_indicator`

Sends one typing indicator pulse to a DM or server channel.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID"
}
```

### `send_attachments`

Sends one message with one or more local file attachments. File paths are read by the MCP server process.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "attachment_paths": ["/absolute/path/to/image.png"],
  "content": "optional message text"
}
```

### `edit_message`

Edits a message owned by the authenticated actor. Discord rejects edits without permission.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "message_id": "MESSAGE_ID",
  "content": "updated text"
}
```

### `delete_message`

Deletes a message the authenticated actor owns or can manage. Discord rejects deletes without permission.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "message_id": "MESSAGE_ID"
}
```

### `add_reaction`

Adds your reaction to a message.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "message_id": "MESSAGE_ID",
  "emoji": "🔥"
}
```

For custom Discord emoji, pass the Discord emoji route shape:

```json
{
  "emoji": "emoji_name:CUSTOM_OR_DISCORD_ID"
}
```

### `remove_reaction`

Removes the authenticated actor's reaction from a message.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "message_id": "MESSAGE_ID",
  "emoji": "🔥"
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

### `collect_dm_burst`

Waits for a DM sender to pause, then returns the batch of new incoming messages. This is the natural-response primitive for avoiding one reply per tiny message.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "after_event_id": 0,
  "quiet_seconds": 5,
  "max_wait_seconds": 30,
  "max_events": 20,
  "respect_typing": true,
  "typing_ttl_seconds": 8
}
```

Behavior:

```text
Wait until at least one new DM message arrives.
If more messages arrive, keep extending the quiet timer.
If Discord TYPING_START arrives and respect_typing=true, keep waiting briefly.
Return once quiet_seconds passes, max_wait_seconds is reached, or max_events is reached.
```

Returns:

```json
{
  "channel_id": "CHANNEL_ID",
  "events": [],
  "last_event_id": 123,
  "ended_reason": "quiet_period",
  "typing_observed": true
}
```

### `start_dm_watch`

Focuses incremental polling on a single DM conversation.

Inputs:

```json
{
  "channel_id": "CHANNEL_ID",
  "context_limit": 30,
  "idle_timeout_seconds": 300
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

## Cron-Style Polling Example

The MCP server does not wake the model itself. For token efficiency, run a tiny non-AI poller and only wake an agent when the poller sees useful events.

```bash
uv run python examples/poll_new_dms.py
```

That script calls `poll_new_dm_events`, stores a local cursor in `.local/poll_new_dms_cursor.json`, and prints compact notification JSON for new DM events.

## Common Agent Instructions

Find a DM with a person:

```text
Call list_dms with query set to the person's username/display name.
Use the returned channel_id for later tools.
```

Read the latest messages:

```text
Call read_messages with channel_id and limit.
Keep compact=true unless the agent needs attachments or reply metadata.
Use message_id from the returned messages for reply/edit/delete/reaction actions.
```

Reply to a specific message:

```text
Call reply_to_message with channel_id, target message_id, and content.
```

React to a message:

```text
Call add_reaction with channel_id, message_id, and emoji.
```

Remove your reaction:

```text
Call remove_reaction with the same channel_id, message_id, and emoji.
```

Wait for someone to finish a multi-message DM thought:

```text
Call collect_dm_burst with quiet_seconds around 3-8 seconds.
Then respond once to the returned batch.
```

Edit a message:

```text
Call edit_message with channel_id, your message_id, and replacement content.
```

Delete a message:

```text
Call delete_message with channel_id and your message_id.
```

Send a human-ish response:

```text
Call send_natural_message. The MCP server handles typing indicators and then sends.
```

Send a file:

```text
Call send_attachments with absolute file paths visible to the MCP server.
```

Find and post in a server channel:

```text
Call list_servers.
Pick guild_id.
Call list_server_channels.
Pick channel_id.
Call read_messages or send_message.
```

Ping in a server:

```text
Use send_message with Discord mention syntax in content, such as <@USER_ID>.
```

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
- REST live testing verified DM lookup and clearly marked smoke-test sending in a private local environment.
- Gateway live test reached `READY` and cached DM channels.
