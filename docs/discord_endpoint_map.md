# Discord Endpoint Map

This map combines:

- typed Discord REST coverage in this Python MCP
- feature names from the Java Discord MCP reference
- a sanitized Agent MCPB recording over `discord.com` filtered to endpoint shapes only

Raw recordings can include tokens, emails, passwords, message content, and other account data.
Do not commit raw capture files. Keep only route shapes, method names, response status counts,
and redacted body-key summaries in this repo.

## Captured Web-Client Session Shapes

The recording showed these route shapes. IDs, bodies, and response payloads were intentionally
redacted.

| Count | Method | Route shape | Statuses | Body keys |
| ---: | --- | --- | --- | --- |
| 21 | POST | `/api/v9/science` | `204` | `events`, `token` |
| 6 | POST | `/api/v9/channels/:channel_id/messages/:message_id/ack` | `401`, `204` | `last_viewed`, `token` |
| 5 | GET | `/api/v9/channels/:channel_id/messages` | `200`, `401` | none |
| 4 | GET | `/api/v9/users/:user_id/profile` | `200`, `401` | none |
| 2 | PUT | `/api/v9/users/@me/relationships/:user_id` | `400`, `204` | `confirm_stranger_request` |
| 1 | GET | `/api/v9/users/@me/relationships` | `200` | none |
| 1 | GET | `/api/v9/guilds/:guild_id/basic` | `404` | none |
| 1 | POST | `/api/v9/channels/:channel_id/typing` | `204` | none |
| 1 | POST | `/api/v9/channels/:channel_id/messages` | `200` | `content`, `flags`, `nonce`, `tts` |
| 1 | GET | `/api/v9/users/@me/entitlements` | `401` | none |
| 1 | GET | `/api/v9/experiments` | `200` | none |
| 1 | PATCH | `/api/v9/users/@me/settings-proto/2` | `401` | redacted |
| 1 | GET | `/api/v9/users/@me` | `401` | none |
| 1 | GET | `/api/v9/auth/location-metadata` | `200` | none |
| 1 | POST | `/api/v9/auth/conditional/start` | `200` | redacted |
| 1 | POST | `/api/v9/auth/login` | `400` | `login`, `password`, `login_source`, `undelete` |

## Message Request Mapping

The observed message-request flow is relationship-based:

1. Read relationships with `GET /users/@me/relationships`.
2. Treat request-like relationship types as candidates. The MCP default filters types `3` and `4`,
   but lets callers pass explicit `relationship_types` because these are client-facing shapes.
3. Accept/confirm a request with:
   `PUT /users/@me/relationships/{user_id}` and body `{"confirm_stranger_request": true}`.
4. Delete a relationship/request with `DELETE /users/@me/relationships/{user_id}`.

MCP tools:

- `list_relationships`
- `list_message_requests`
- `poll_message_requests`
- `accept_message_request`
- `delete_relationship`
- `get_user_profile`
- `ack_message`

To know whether a new message request appeared, call `poll_message_requests` with the previous
`request_user_ids`; it returns both the full request list and `new_requests`.

## Server Creation Mapping

Discord's stable app-facing server automation is template-based or invite/blueprint based:

- `create_server` requires `template_code` and calls the template route.
- `create_server_from_template` calls `POST /guilds/templates/{template_code}`.
- `apply_server_blueprint` builds roles/categories/channels inside an existing server.
- `get_bot_invite_url` generates the OAuth2 invite URL for adding the bot to a server.

Blank server creation is not treated as a dependable bot-token operation here. If Discord rejects
template creation for the current token, create the server manually, invite the bot, then run a
blueprint.

## Java MCP Coverage Ported

The active Python MCP now covers the major Java MCP surfaces:

- server/guild info, widgets, welcome screen, onboarding, vanity URL, regions, leave server
- channels, categories, stage/voice/forum channels, channel move, channel info/search
- channel permission overwrites for roles and members
- messages, replies, pins, bulk delete, crosspost, reactions, attachments
- DMs by channel ID and private-message helpers by user ID
- roles, member lookup/search/add, member roles, nickname, timeouts, bans, kicks
- voice member move/disconnect and server mute/deafen
- invites and guild templates
- scheduled events and event users
- emojis
- webhooks, including webhook execution by ID/token
- active thread listing and forum post/thread management
- a guarded `discord_api_request` escape hatch for unwrapped Discord API paths

## Boundaries

This MCP does not extract Discord tokens from browsers, run login flows, replay passwords, or commit
captured traffic. Provide tokens explicitly through `DISCORD_TOKEN_FILE`, and use
`ALLOW_SEND=false` for read-only exploration.
