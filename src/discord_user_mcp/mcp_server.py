from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from discord_user_mcp.config import Settings
from discord_user_mcp.services.runtime import DiscordUserMcpRuntime


@asynccontextmanager
async def _lifespan(runtime: DiscordUserMcpRuntime) -> AsyncIterator[dict[str, object]]:
    await runtime.start()
    try:
        yield {"runtime": runtime}
    finally:
        # FastMCP can enter/exit this lifespan around streamable HTTP sessions.
        # Keep the Discord runtime process-scoped so a client disconnect does not
        # close the REST client, SQLite store, or live Gateway watcher.
        pass


def create_mcp(
    settings: Settings | None = None,
    runtime: DiscordUserMcpRuntime | None = None,
) -> FastMCP:
    settings = settings or Settings.from_env()
    runtime = runtime or DiscordUserMcpRuntime.from_settings(settings)

    mcp = FastMCP(
        "discord-user-dm-mcp",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        lifespan=lambda _: _lifespan(runtime),
    )

    @mcp.tool(name="discord_status", description="Get Discord Gateway and MCP runtime status.")
    async def discord_status() -> dict:
        return await runtime.status()

    @mcp.tool(
        name="list_dms",
        description="List direct message channels visible to the user session.",
    )
    async def list_dms(
        limit: int = 50,
        query: str | None = None,
        refresh: bool = True,
    ) -> list[dict]:
        return await runtime.list_dms(limit=limit, query=query, refresh=refresh)

    @mcp.tool(
        name="list_servers",
        description="List Discord servers/guilds visible to the user session.",
    )
    async def list_servers(limit: int = 100, query: str | None = None) -> list[dict]:
        return await runtime.list_servers(limit=limit, query=query)

    @mcp.tool(
        name="list_server_channels",
        description="List text-like channels for a Discord server/guild.",
    )
    async def list_server_channels(
        guild_id: str,
        limit: int = 100,
        query: str | None = None,
    ) -> list[dict]:
        return await runtime.list_server_channels(guild_id, limit=limit, query=query)

    @mcp.tool(
        name="read_messages",
        description=(
            "Read recent messages from a DM or server channel. Defaults to compact "
            "token-efficient rows: person, message, time, ids."
        ),
    )
    async def read_messages(
        channel_id: str,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        compact: bool = True,
    ) -> list[dict]:
        return await runtime.read_messages(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
            compact=compact,
        )

    @mcp.tool(
        name="send_message",
        description=(
            "Send a normal message to a DM or server channel. Server pings are plain "
            "Discord mention text like <@USER_ID> or <@&ROLE_ID>."
        ),
    )
    async def send_message(channel_id: str, content: str) -> dict:
        return await runtime.send_message(channel_id, content)

    @mcp.tool(
        name="send_natural_message",
        description=(
            "Send typing indicators based on WPM, then send a message to any DM or "
            "server channel."
        ),
    )
    async def send_natural_message(
        channel_id: str,
        content: str,
        wpm: int | None = None,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> dict:
        return await runtime.send_natural_message(
            channel_id,
            content,
            wpm=wpm,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )

    @mcp.tool(
        name="reply_to_message",
        description="Reply to a specific message in a DM or server channel.",
    )
    async def reply_to_message(channel_id: str, message_id: str, content: str) -> dict:
        return await runtime.reply_to_message(channel_id, message_id, content)

    @mcp.tool(name="edit_message", description="Edit one of your messages in any channel.")
    async def edit_message(channel_id: str, message_id: str, content: str) -> dict:
        return await runtime.edit_dm_message(channel_id, message_id, content)

    @mcp.tool(name="delete_message", description="Delete one of your messages in any channel.")
    async def delete_message(channel_id: str, message_id: str) -> dict:
        return await runtime.delete_message(channel_id, message_id)

    @mcp.tool(name="add_reaction", description="Add your reaction to a message.")
    async def add_reaction(channel_id: str, message_id: str, emoji: str) -> dict:
        return await runtime.add_message_reaction(channel_id, message_id, emoji)

    @mcp.tool(name="remove_reaction", description="Remove your reaction from a message.")
    async def remove_reaction(channel_id: str, message_id: str, emoji: str) -> dict:
        return await runtime.remove_message_reaction(channel_id, message_id, emoji)

    @mcp.tool(
        name="send_typing_indicator",
        description="Send one Discord typing indicator pulse to a DM or server channel.",
    )
    async def send_typing_indicator(channel_id: str) -> dict:
        return await runtime.send_typing_indicator(channel_id)

    @mcp.tool(
        name="send_attachments",
        description="Send one message with one or more local file attachments.",
    )
    async def send_attachments(
        channel_id: str,
        attachment_paths: list[str],
        content: str | None = None,
    ) -> dict:
        return await runtime.send_attachments(
            channel_id,
            attachment_paths=attachment_paths,
            content=content,
        )

    @mcp.tool(name="poll_new_dm_events", description="Poll incoming DM events captured by Gateway.")
    async def poll_new_dm_events(
        after_event_id: int = 0,
        limit: int = 20,
        channel_id: str | None = None,
    ) -> list[dict]:
        return await runtime.poll_new_dm_events(
            after_event_id=after_event_id,
            limit=limit,
            channel_id=channel_id,
        )

    @mcp.tool(
        name="collect_dm_burst",
        description="Wait for a DM sender to pause, then return the batch of new messages.",
    )
    async def collect_dm_burst(
        channel_id: str,
        after_event_id: int = 0,
        quiet_seconds: float = 5,
        max_wait_seconds: float = 30,
        max_events: int = 20,
        respect_typing: bool = True,
        typing_ttl_seconds: float = 8,
    ) -> dict:
        return await runtime.collect_dm_burst(
            channel_id,
            after_event_id=after_event_id,
            quiet_seconds=quiet_seconds,
            max_wait_seconds=max_wait_seconds,
            max_events=max_events,
            respect_typing=respect_typing,
            typing_ttl_seconds=typing_ttl_seconds,
        )

    @mcp.tool(
        name="start_dm_watch",
        description="Focus incremental event polling on one DM channel.",
    )
    def start_dm_watch(
        channel_id: str,
        context_limit: int = 30,
        idle_timeout_seconds: int = 300,
    ) -> dict:
        return runtime.start_dm_watch(
            channel_id,
            context_limit=context_limit,
            idle_timeout_seconds=idle_timeout_seconds,
        )

    @mcp.tool(
        name="poll_active_dm",
        description="Poll incremental events for the active watched DM.",
    )
    async def poll_active_dm(wait_seconds: float = 0, max_events: int = 10) -> dict:
        return await runtime.poll_active_dm(wait_seconds=wait_seconds, max_events=max_events)

    @mcp.tool(name="stop_dm_watch", description="Stop the active DM watch.")
    def stop_dm_watch() -> dict:
        return runtime.stop_dm_watch()

    return mcp
