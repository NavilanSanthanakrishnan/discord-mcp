from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

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
        name="get_custom_status",
        description="Read the account's current presence status and custom status text/emoji.",
    )
    async def get_custom_status() -> dict:
        return await runtime.get_custom_status()

    @mcp.tool(
        name="set_custom_status",
        description=(
            "Set or clear the account custom status. Text, unicode emoji_name, "
            "custom emoji_id, and ISO expires_at are optional."
        ),
    )
    async def set_custom_status(
        text: str | None = None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict:
        return await runtime.set_custom_status(
            text=text,
            emoji_name=emoji_name,
            emoji_id=emoji_id,
            expires_at=expires_at,
        )

    @mcp.tool(
        name="discord_api_request",
        description=(
            "Call an official Discord API path with the configured Authorization header. "
            "Use for supported bot/OAuth endpoints not yet wrapped by a typed tool."
        ),
    )
    async def discord_api_request(
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        audit_log_reason: str | None = None,
    ) -> Any:
        return await runtime.discord_api_request(
            method,
            path,
            params=params,
            json_body=json_body,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_current_user", description="Get the authenticated Discord user or bot.")
    async def get_current_user() -> dict:
        return await runtime.get_current_user()

    @mcp.tool(name="get_current_bot", description="Alias for get_current_user.")
    async def get_current_bot() -> dict:
        return await runtime.get_current_user()

    @mcp.tool(name="get_bot_invite_url", description="Generate an OAuth2 URL to invite this bot.")
    async def get_bot_invite_url(
        permissions: str = "0",
        guild_id: str | None = None,
        scopes: str = "bot applications.commands",
    ) -> dict:
        return await runtime.get_bot_invite_url(
            permissions=permissions,
            guild_id=guild_id,
            scopes=scopes,
        )

    @mcp.tool(
        name="list_relationships",
        description="List Discord relationship rows visible to the current session.",
    )
    async def list_relationships(relationship_type: int | None = None) -> list[dict]:
        return await runtime.list_relationships(relationship_type=relationship_type)

    @mcp.tool(
        name="list_message_requests",
        description=(
            "List relationship rows that behave like incoming or outgoing message requests."
        ),
    )
    async def list_message_requests(
        relationship_types: list[int] | None = None,
    ) -> list[dict]:
        return await runtime.list_message_requests(relationship_types=relationship_types)

    @mcp.tool(
        name="poll_message_requests",
        description="List message requests and mark which user IDs were not in known_user_ids.",
    )
    async def poll_message_requests(
        known_user_ids: list[str] | None = None,
        relationship_types: list[int] | None = None,
    ) -> dict:
        return await runtime.poll_message_requests(
            known_user_ids=known_user_ids,
            relationship_types=relationship_types,
        )

    @mcp.tool(
        name="accept_message_request",
        description="Accept/confirm a captured Discord message request for a user ID.",
    )
    async def accept_message_request(user_id: str) -> dict | None:
        return await runtime.accept_message_request(user_id)

    @mcp.tool(
        name="delete_relationship",
        description="Delete a relationship row, such as a friend, request, or block entry.",
    )
    async def delete_relationship(user_id: str) -> dict | None:
        return await runtime.delete_relationship(user_id)

    @mcp.tool(name="get_user_profile", description="Get a Discord user profile by user ID.")
    async def get_user_profile(user_id: str) -> dict:
        return await runtime.get_user_profile(user_id)

    @mcp.tool(
        name="ack_message",
        description="Mark a message as acknowledged/read for auth contexts that support the route.",
    )
    async def ack_message(
        channel_id: str,
        message_id: str,
        last_viewed: int | None = None,
        ack_token: str | None = None,
    ) -> dict | None:
        return await runtime.ack_message(
            channel_id,
            message_id,
            last_viewed=last_viewed,
            ack_token=ack_token,
        )

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

    @mcp.tool(name="create_dm_channel", description="Open or create a DM channel with a user ID.")
    async def create_dm_channel(user_id: str) -> dict:
        return await runtime.create_dm_channel(user_id)

    @mcp.tool(name="send_private_message", description="Send a DM to a user ID.")
    async def send_private_message(user_id: str, content: str) -> dict:
        return await runtime.send_private_message(user_id, content)

    @mcp.tool(name="read_private_messages", description="Read DM messages by user ID.")
    async def read_private_messages(
        user_id: str,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        compact: bool = True,
    ) -> list[dict]:
        return await runtime.read_private_messages(
            user_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
            compact=compact,
        )

    @mcp.tool(name="edit_private_message", description="Edit one of your DM messages by user ID.")
    async def edit_private_message(user_id: str, message_id: str, content: str) -> dict:
        return await runtime.edit_private_message(user_id, message_id, content)

    @mcp.tool(
        name="delete_private_message",
        description="Delete one of your DM messages by user ID.",
    )
    async def delete_private_message(user_id: str, message_id: str) -> dict:
        return await runtime.delete_private_message(user_id, message_id)

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

    @mcp.tool(name="get_server_info", description="Get detailed server/guild information.")
    async def get_server_info(guild_id: str, with_counts: bool = True) -> dict:
        return await runtime.get_server_info(guild_id, with_counts=with_counts)

    @mcp.tool(
        name="list_all_server_channels",
        description=(
            "List every server channel type, including categories, voice, forums, "
            "and announcements."
        ),
    )
    async def list_all_server_channels(guild_id: str) -> list[dict]:
        return await runtime.list_all_server_channels(guild_id)

    @mcp.tool(name="list_channels", description="Alias for list_all_server_channels.")
    async def list_channels(guild_id: str) -> list[dict]:
        return await runtime.list_all_server_channels(guild_id)

    @mcp.tool(
        name="list_active_threads",
        description="List active public and private threads in a server.",
    )
    async def list_active_threads(guild_id: str) -> dict:
        return await runtime.list_active_threads(guild_id)

    @mcp.tool(
        name="create_server",
        description=(
            "Create a server from a guild template. Pass template_code; blank server creation "
            "is not generally available to bot tokens."
        ),
    )
    async def create_server(
        name: str,
        template_code: str | None = None,
        icon: str | None = None,
    ) -> dict:
        return await runtime.create_server(name, template_code=template_code, icon=icon)

    @mcp.tool(
        name="create_server_from_template",
        description="Create a server/guild from a Discord guild template code.",
    )
    async def create_server_from_template(
        template_code: str,
        name: str,
        icon: str | None = None,
    ) -> dict:
        return await runtime.create_server_from_template(template_code, name=name, icon=icon)

    @mcp.tool(name="get_server_preview", description="Get public preview data for a server.")
    async def get_server_preview(guild_id: str) -> dict:
        return await runtime.get_server_preview(guild_id)

    @mcp.tool(
        name="list_server_voice_regions",
        description="List voice regions available to a server.",
    )
    async def list_server_voice_regions(guild_id: str) -> list[dict]:
        return await runtime.list_server_voice_regions(guild_id)

    @mcp.tool(name="get_server_vanity_url", description="Get a server vanity URL.")
    async def get_server_vanity_url(guild_id: str) -> dict:
        return await runtime.get_server_vanity_url(guild_id)

    @mcp.tool(name="get_server_widget", description="Get server widget settings.")
    async def get_server_widget(guild_id: str) -> dict:
        return await runtime.get_server_widget(guild_id)

    @mcp.tool(name="get_server_widget_json", description="Get the public server widget JSON.")
    async def get_server_widget_json(guild_id: str) -> dict:
        return await runtime.get_server_widget_json(guild_id)

    @mcp.tool(name="edit_server_widget", description="Enable/disable the server widget.")
    async def edit_server_widget(
        guild_id: str,
        enabled: bool,
        channel_id: str | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_server_widget(
            guild_id,
            enabled=enabled,
            channel_id=channel_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_welcome_screen", description="Get the server welcome screen.")
    async def get_welcome_screen(guild_id: str) -> dict:
        return await runtime.get_welcome_screen(guild_id)

    @mcp.tool(
        name="edit_welcome_screen",
        description="Modify a server welcome screen with official Discord fields.",
    )
    async def edit_welcome_screen(
        guild_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_welcome_screen(
            guild_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_server_onboarding", description="Get server onboarding configuration.")
    async def get_server_onboarding(guild_id: str) -> dict:
        return await runtime.get_server_onboarding(guild_id)

    @mcp.tool(
        name="edit_server_onboarding",
        description="Modify server onboarding configuration with official Discord fields.",
    )
    async def edit_server_onboarding(
        guild_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_server_onboarding(
            guild_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="leave_server",
        description="Leave a server only when confirm_server_name exactly matches its name.",
    )
    async def leave_server(guild_id: str, confirm_server_name: str) -> dict | None:
        return await runtime.leave_server(guild_id, confirm_server_name=confirm_server_name)

    @mcp.tool(
        name="edit_server_settings",
        description="Modify server settings with official Discord guild fields.",
    )
    async def edit_server_settings(
        guild_id: str,
        settings: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_server_settings(
            guild_id,
            settings,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_audit_log", description="Read server audit log entries.")
    async def get_audit_log(
        guild_id: str,
        user_id: str | None = None,
        action_type: int | None = None,
        before: str | None = None,
        limit: int = 50,
    ) -> dict:
        return await runtime.get_audit_log(
            guild_id,
            user_id=user_id,
            action_type=action_type,
            before=before,
            limit=limit,
        )

    @mcp.tool(name="create_text_channel", description="Create a text channel in a server.")
    async def create_text_channel(
        guild_id: str,
        name: str,
        topic: str | None = None,
        parent_id: str | None = None,
        nsfw: bool | None = None,
        rate_limit_per_user: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_text_channel(
            guild_id,
            name,
            topic=topic,
            parent_id=parent_id,
            nsfw=nsfw,
            rate_limit_per_user=rate_limit_per_user,
            position=position,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="create_voice_channel", description="Create a voice channel in a server.")
    async def create_voice_channel(
        guild_id: str,
        name: str,
        parent_id: str | None = None,
        bitrate: int | None = None,
        user_limit: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_voice_channel(
            guild_id,
            name,
            parent_id=parent_id,
            bitrate=bitrate,
            user_limit=user_limit,
            position=position,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="create_stage_channel", description="Create a stage channel in a server.")
    async def create_stage_channel(
        guild_id: str,
        name: str,
        parent_id: str | None = None,
        bitrate: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_stage_channel(
            guild_id,
            name,
            parent_id=parent_id,
            bitrate=bitrate,
            position=position,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="create_category", description="Create a channel category in a server.")
    async def create_category(
        guild_id: str,
        name: str,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_category(
            guild_id,
            name,
            position=position,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="create_forum_channel", description="Create a forum channel in a server.")
    async def create_forum_channel(
        guild_id: str,
        name: str,
        topic: str | None = None,
        parent_id: str | None = None,
        nsfw: bool | None = None,
        rate_limit_per_user: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_forum_channel(
            guild_id,
            name,
            topic=topic,
            parent_id=parent_id,
            nsfw=nsfw,
            rate_limit_per_user=rate_limit_per_user,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="edit_forum_channel",
        description="Edit a forum channel with official Discord channel fields.",
    )
    async def edit_forum_channel(
        channel_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_forum_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_channel_info", description="Get detailed channel information.")
    async def get_channel_info(channel_id: str) -> dict:
        return await runtime.get_channel_info(channel_id)

    @mcp.tool(name="find_channel", description="Find channels in a server by name substring.")
    async def find_channel(
        guild_id: str,
        query: str,
        channel_type: int | None = None,
    ) -> list[dict]:
        return await runtime.find_channel(guild_id, query, channel_type=channel_type)

    @mcp.tool(name="find_category", description="Find category channels by name substring.")
    async def find_category(guild_id: str, query: str) -> list[dict]:
        return await runtime.find_channel(guild_id, query, channel_type=4)

    @mcp.tool(
        name="list_channels_in_category",
        description="List channels inside a category.",
    )
    async def list_channels_in_category(guild_id: str, category_id: str) -> list[dict]:
        return await runtime.list_channels_in_category(guild_id, category_id)

    @mcp.tool(
        name="move_channel",
        description="Move a channel to a position and/or category.",
    )
    async def move_channel(
        guild_id: str,
        channel_id: str,
        position: int | None = None,
        parent_id: str | None = None,
        lock_permissions: bool | None = None,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.move_channel(
            guild_id,
            channel_id,
            position=position,
            parent_id=parent_id,
            lock_permissions=lock_permissions,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="list_channel_permission_overwrites",
        description="List role/member permission overwrites for a channel.",
    )
    async def list_channel_permission_overwrites(channel_id: str) -> list[dict]:
        return await runtime.list_channel_permission_overwrites(channel_id)

    @mcp.tool(
        name="upsert_channel_permission_overwrite",
        description="Create or update a role/member permission overwrite for a channel.",
    )
    async def upsert_channel_permission_overwrite(
        channel_id: str,
        overwrite_id: str,
        overwrite_type: int,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.upsert_channel_permission_overwrite(
            channel_id,
            overwrite_id,
            overwrite_type=overwrite_type,
            allow=allow,
            deny=deny,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="upsert_role_channel_permissions",
        description="Create or update a role permission overwrite for a channel.",
    )
    async def upsert_role_channel_permissions(
        channel_id: str,
        role_id: str,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.upsert_role_channel_permissions(
            channel_id,
            role_id,
            allow=allow,
            deny=deny,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="upsert_member_channel_permissions",
        description="Create or update a member permission overwrite for a channel.",
    )
    async def upsert_member_channel_permissions(
        channel_id: str,
        user_id: str,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.upsert_member_channel_permissions(
            channel_id,
            user_id,
            allow=allow,
            deny=deny,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="delete_channel_permission_overwrite",
        description="Delete a channel permission overwrite.",
    )
    async def delete_channel_permission_overwrite(
        channel_id: str,
        overwrite_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.delete_channel_permission_overwrite(
            channel_id,
            overwrite_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="list_forum_channels", description="List forum/media channels in a server.")
    async def list_forum_channels(guild_id: str) -> list[dict]:
        return await runtime.list_forum_channels(guild_id)

    @mcp.tool(name="get_forum_channel_info", description="Get forum channel details.")
    async def get_forum_channel_info(forum_channel_id: str) -> dict:
        return await runtime.get_forum_channel_info(forum_channel_id)

    @mcp.tool(name="list_forum_tags", description="List tags available in a forum channel.")
    async def list_forum_tags(forum_channel_id: str) -> list[dict]:
        return await runtime.list_forum_tags(forum_channel_id)

    @mcp.tool(name="create_forum_post", description="Create a forum post/thread.")
    async def create_forum_post(
        forum_channel_id: str,
        name: str,
        content: str,
        applied_tags: list[str] | None = None,
        embeds: list[dict[str, Any]] | None = None,
        auto_archive_duration: int | None = None,
        rate_limit_per_user: int | None = None,
    ) -> dict:
        return await runtime.create_forum_post(
            forum_channel_id,
            name=name,
            content=content,
            applied_tags=applied_tags,
            embeds=embeds,
            auto_archive_duration=auto_archive_duration,
            rate_limit_per_user=rate_limit_per_user,
        )

    @mcp.tool(name="list_forum_posts", description="List forum posts/threads.")
    async def list_forum_posts(
        forum_channel_id: str,
        guild_id: str | None = None,
        include_archived: bool = True,
    ) -> dict:
        return await runtime.list_forum_posts(
            forum_channel_id,
            guild_id=guild_id,
            include_archived=include_archived,
        )

    @mcp.tool(name="modify_forum_post", description="Modify forum post/thread settings.")
    async def modify_forum_post(
        thread_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.modify_forum_post(
            thread_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="edit_channel",
        description="Edit a channel with official Discord channel fields.",
    )
    async def edit_channel(
        channel_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="edit_text_channel", description="Alias for edit_channel.")
    async def edit_text_channel(
        channel_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="edit_voice_channel", description="Alias for edit_channel.")
    async def edit_voice_channel(
        channel_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="edit_category", description="Alias for edit_channel.")
    async def edit_category(
        channel_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="delete_channel", description="Delete a channel.")
    async def delete_channel(channel_id: str, audit_log_reason: str | None = None) -> dict:
        return await runtime.delete_channel(channel_id, audit_log_reason=audit_log_reason)

    @mcp.tool(name="delete_category", description="Alias for delete_channel.")
    async def delete_category(channel_id: str, audit_log_reason: str | None = None) -> dict:
        return await runtime.delete_channel(channel_id, audit_log_reason=audit_log_reason)

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

    @mcp.tool(name="pin_message", description="Pin a message in a channel.")
    async def pin_message(
        channel_id: str,
        message_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.pin_message(
            channel_id,
            message_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="unpin_message", description="Unpin a message in a channel.")
    async def unpin_message(
        channel_id: str,
        message_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.unpin_message(
            channel_id,
            message_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="bulk_delete_messages", description="Bulk delete 2-100 messages from a channel.")
    async def bulk_delete_messages(
        channel_id: str,
        message_ids: list[str],
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.bulk_delete_messages(
            channel_id,
            message_ids,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(
        name="crosspost_message",
        description="Publish/crosspost an announcement-channel message.",
    )
    async def crosspost_message(channel_id: str, message_id: str) -> dict:
        return await runtime.crosspost_message(channel_id, message_id)

    @mcp.tool(name="get_message", description="Get one raw Discord message by ID.")
    async def get_message(channel_id: str, message_id: str) -> dict:
        return await runtime.get_message(channel_id, message_id)

    @mcp.tool(
        name="get_attachment",
        description=(
            "Get attachment metadata from one message, or all attachments if no ID is given."
        ),
    )
    async def get_attachment(
        channel_id: str,
        message_id: str,
        attachment_id: str | None = None,
    ) -> dict | list[dict]:
        return await runtime.get_attachment(channel_id, message_id, attachment_id)

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

    @mcp.tool(name="list_roles", description="List server roles.")
    async def list_roles(guild_id: str) -> list[dict]:
        return await runtime.list_roles(guild_id)

    @mcp.tool(
        name="create_role",
        description="Create a server role with official Discord role fields.",
    )
    async def create_role(
        guild_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_role(
            guild_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="edit_role", description="Edit a server role with official Discord role fields.")
    async def edit_role(
        guild_id: str,
        role_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_role(
            guild_id,
            role_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="delete_role", description="Delete a server role.")
    async def delete_role(
        guild_id: str,
        role_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.delete_role(
            guild_id,
            role_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="assign_role", description="Assign a role to a server member.")
    async def assign_role(
        guild_id: str,
        user_id: str,
        role_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.assign_role(
            guild_id,
            user_id,
            role_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="remove_role", description="Remove a role from a server member.")
    async def remove_role(
        guild_id: str,
        user_id: str,
        role_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.remove_role(
            guild_id,
            user_id,
            role_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_member", description="Get a server member.")
    async def get_member(guild_id: str, user_id: str) -> dict:
        return await runtime.get_member(guild_id, user_id)

    @mcp.tool(name="get_member_info", description="Alias for get_member.")
    async def get_member_info(guild_id: str, user_id: str) -> dict:
        return await runtime.get_member(guild_id, user_id)

    @mcp.tool(name="list_members", description="List server members with official API pagination.")
    async def list_members(
        guild_id: str,
        limit: int = 100,
        after: str | None = None,
    ) -> list[dict]:
        return await runtime.list_members(guild_id, limit=limit, after=after)

    @mcp.tool(
        name="search_members",
        description="Search server members by username/nickname prefix.",
    )
    async def search_members(guild_id: str, query: str, limit: int = 25) -> list[dict]:
        return await runtime.search_members(guild_id, query, limit=limit)

    @mcp.tool(
        name="get_user_id_by_name",
        description="Search server members by name and return candidate user IDs.",
    )
    async def get_user_id_by_name(
        username: str,
        guild_id: str,
        limit: int = 25,
    ) -> list[dict]:
        return await runtime.get_user_id_by_name(guild_id, username, limit=limit)

    @mcp.tool(
        name="add_member_to_server",
        description=(
            "Add a user to a server with an OAuth2 access token that has guilds.join. "
            "This is not a Discord user-session token."
        ),
    )
    async def add_member_to_server(
        guild_id: str,
        user_id: str,
        access_token: str,
        nick: str | None = None,
        roles: list[str] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
    ) -> dict | None:
        return await runtime.add_member_to_server(
            guild_id,
            user_id,
            access_token=access_token,
            nick=nick,
            roles=roles,
            mute=mute,
            deaf=deaf,
        )

    @mcp.tool(name="list_member_roles", description="List role IDs assigned to a member.")
    async def list_member_roles(guild_id: str, user_id: str) -> list[str]:
        return await runtime.list_member_roles(guild_id, user_id)

    @mcp.tool(
        name="modify_member",
        description="Modify a server member with official Discord fields.",
    )
    async def modify_member(
        guild_id: str,
        user_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.modify_member(
            guild_id,
            user_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="set_nickname", description="Set or clear a member nickname.")
    async def set_nickname(
        guild_id: str,
        user_id: str,
        nick: str | None = None,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.set_nickname(
            guild_id,
            user_id,
            nick=nick,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="move_member", description="Move a member to a voice/stage channel.")
    async def move_member(
        guild_id: str,
        user_id: str,
        channel_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.move_member(
            guild_id,
            user_id,
            channel_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="disconnect_member", description="Disconnect a member from voice.")
    async def disconnect_member(
        guild_id: str,
        user_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.disconnect_member(
            guild_id,
            user_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="modify_voice_state", description="Server mute/deafen a member.")
    async def modify_voice_state(
        guild_id: str,
        user_id: str,
        mute: bool | None = None,
        deaf: bool | None = None,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.modify_voice_state(
            guild_id,
            user_id,
            mute=mute,
            deaf=deaf,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="timeout_member", description="Timeout a server member for up to 28 days.")
    async def timeout_member(
        guild_id: str,
        user_id: str,
        duration_seconds: int,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.timeout_member(
            guild_id,
            user_id,
            duration_seconds=duration_seconds,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="remove_timeout", description="Remove a member timeout.")
    async def remove_timeout(
        guild_id: str,
        user_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.remove_timeout(
            guild_id,
            user_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="kick_member", description="Kick a member from a server.")
    async def kick_member(
        guild_id: str,
        user_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.kick_member(guild_id, user_id, audit_log_reason=audit_log_reason)

    @mcp.tool(name="ban_member", description="Ban a member from a server.")
    async def ban_member(
        guild_id: str,
        user_id: str,
        delete_message_seconds: int = 0,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.ban_member(
            guild_id,
            user_id,
            delete_message_seconds=delete_message_seconds,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="unban_member", description="Remove a server ban.")
    async def unban_member(
        guild_id: str,
        user_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.unban_member(guild_id, user_id, audit_log_reason=audit_log_reason)

    @mcp.tool(name="list_bans", description="List server bans.")
    async def list_bans(
        guild_id: str,
        limit: int = 1000,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        return await runtime.list_bans(guild_id, limit=limit, before=before, after=after)

    @mcp.tool(name="get_bans", description="Alias for list_bans.")
    async def get_bans(
        guild_id: str,
        limit: int = 1000,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        return await runtime.list_bans(guild_id, limit=limit, before=before, after=after)

    @mcp.tool(
        name="list_guild_scheduled_events",
        description="List active and scheduled server events.",
    )
    async def list_guild_scheduled_events(
        guild_id: str,
        with_user_count: bool = True,
    ) -> list[dict]:
        return await runtime.list_guild_scheduled_events(
            guild_id,
            with_user_count=with_user_count,
        )

    @mcp.tool(name="create_guild_scheduled_event", description="Create a server event.")
    async def create_guild_scheduled_event(
        guild_id: str,
        name: str,
        scheduled_start_time: str,
        entity_type: int,
        channel_id: str | None = None,
        scheduled_end_time: str | None = None,
        description: str | None = None,
        entity_metadata: dict[str, Any] | None = None,
        privacy_level: int = 2,
        image: str | None = None,
        recurrence_rule: dict[str, Any] | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_guild_scheduled_event(
            guild_id,
            name=name,
            scheduled_start_time=scheduled_start_time,
            entity_type=entity_type,
            channel_id=channel_id,
            scheduled_end_time=scheduled_end_time,
            description=description,
            entity_metadata=entity_metadata,
            privacy_level=privacy_level,
            image=image,
            recurrence_rule=recurrence_rule,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_guild_scheduled_event", description="Get one server event.")
    async def get_guild_scheduled_event(
        guild_id: str,
        event_id: str,
        with_user_count: bool = True,
    ) -> dict:
        return await runtime.get_guild_scheduled_event(
            guild_id,
            event_id,
            with_user_count=with_user_count,
        )

    @mcp.tool(name="edit_guild_scheduled_event", description="Edit a server event.")
    async def edit_guild_scheduled_event(
        guild_id: str,
        event_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_guild_scheduled_event(
            guild_id,
            event_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="delete_guild_scheduled_event", description="Delete a server event.")
    async def delete_guild_scheduled_event(guild_id: str, event_id: str) -> dict | None:
        return await runtime.delete_guild_scheduled_event(guild_id, event_id)

    @mcp.tool(
        name="get_guild_scheduled_event_users",
        description="List users subscribed/interested in a server event.",
    )
    async def get_guild_scheduled_event_users(
        guild_id: str,
        event_id: str,
        limit: int = 100,
        with_member: bool = False,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        return await runtime.get_guild_scheduled_event_users(
            guild_id,
            event_id,
            limit=limit,
            with_member=with_member,
            before=before,
            after=after,
        )

    @mcp.tool(name="create_invite", description="Create an invite for a channel.")
    async def create_invite(
        channel_id: str,
        max_age: int = 86400,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = False,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_invite(
            channel_id,
            max_age=max_age,
            max_uses=max_uses,
            temporary=temporary,
            unique=unique,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="get_invite", description="Get invite details by code or URL.")
    async def get_invite(invite_code: str, with_counts: bool = True) -> dict:
        return await runtime.get_invite(invite_code, with_counts=with_counts)

    @mcp.tool(name="get_invite_details", description="Alias for get_invite.")
    async def get_invite_details(invite_code: str, with_counts: bool = True) -> dict:
        return await runtime.get_invite(invite_code, with_counts=with_counts)

    @mcp.tool(name="list_invites", description="List active server invites.")
    async def list_invites(guild_id: str) -> list[dict]:
        return await runtime.list_invites(guild_id)

    @mcp.tool(name="delete_invite", description="Delete/revoke an invite.")
    async def delete_invite(
        invite_code: str,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.delete_invite(invite_code, audit_log_reason=audit_log_reason)

    @mcp.tool(name="get_guild_template", description="Get a guild template by code or URL.")
    async def get_guild_template(template_code: str) -> dict:
        return await runtime.get_guild_template(template_code)

    @mcp.tool(name="list_guild_templates", description="List templates for a server.")
    async def list_guild_templates(guild_id: str) -> list[dict]:
        return await runtime.list_guild_templates(guild_id)

    @mcp.tool(name="create_guild_template", description="Create a guild template.")
    async def create_guild_template(
        guild_id: str,
        name: str,
        description: str | None = None,
    ) -> dict:
        return await runtime.create_guild_template(guild_id, name, description=description)

    @mcp.tool(name="sync_guild_template", description="Sync a guild template.")
    async def sync_guild_template(guild_id: str, template_code: str) -> dict:
        return await runtime.sync_guild_template(guild_id, template_code)

    @mcp.tool(name="edit_guild_template", description="Edit guild template metadata.")
    async def edit_guild_template(
        guild_id: str,
        template_code: str,
        fields: dict[str, Any],
    ) -> dict:
        return await runtime.edit_guild_template(guild_id, template_code, fields)

    @mcp.tool(name="delete_guild_template", description="Delete a guild template.")
    async def delete_guild_template(guild_id: str, template_code: str) -> dict:
        return await runtime.delete_guild_template(guild_id, template_code)

    @mcp.tool(name="list_emojis", description="List custom emojis in a server.")
    async def list_emojis(guild_id: str) -> list[dict]:
        return await runtime.list_emojis(guild_id)

    @mcp.tool(name="get_emoji", description="Get one custom emoji by ID.")
    async def get_emoji(guild_id: str, emoji_id: str) -> dict:
        return await runtime.get_emoji(guild_id, emoji_id)

    @mcp.tool(name="get_emoji_details", description="Alias for get_emoji.")
    async def get_emoji_details(guild_id: str, emoji_id: str) -> dict:
        return await runtime.get_emoji(guild_id, emoji_id)

    @mcp.tool(
        name="create_emoji",
        description="Create a custom emoji from image data URI or a local image_path.",
    )
    async def create_emoji(
        guild_id: str,
        name: str,
        image: str | None = None,
        image_path: str | None = None,
        roles: list[str] | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_emoji(
            guild_id,
            name=name,
            image=image,
            image_path=image_path,
            roles=roles,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="edit_emoji", description="Edit a custom emoji.")
    async def edit_emoji(
        guild_id: str,
        emoji_id: str,
        fields: dict[str, Any],
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.edit_emoji(
            guild_id,
            emoji_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="delete_emoji", description="Delete a custom emoji.")
    async def delete_emoji(
        guild_id: str,
        emoji_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.delete_emoji(
            guild_id,
            emoji_id,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="create_webhook", description="Create a channel webhook.")
    async def create_webhook(
        channel_id: str,
        name: str,
        avatar: str | None = None,
        audit_log_reason: str | None = None,
    ) -> dict:
        return await runtime.create_webhook(
            channel_id,
            name,
            avatar=avatar,
            audit_log_reason=audit_log_reason,
        )

    @mcp.tool(name="list_channel_webhooks", description="List webhooks in a channel.")
    async def list_channel_webhooks(channel_id: str) -> list[dict]:
        return await runtime.list_channel_webhooks(channel_id)

    @mcp.tool(name="list_guild_webhooks", description="List webhooks in a server.")
    async def list_guild_webhooks(guild_id: str) -> list[dict]:
        return await runtime.list_guild_webhooks(guild_id)

    @mcp.tool(name="list_webhooks", description="Alias for list_channel_webhooks.")
    async def list_webhooks(channel_id: str) -> list[dict]:
        return await runtime.list_webhooks(channel_id)

    @mcp.tool(name="get_webhook", description="Get a webhook by ID.")
    async def get_webhook(webhook_id: str) -> dict:
        return await runtime.get_webhook(webhook_id)

    @mcp.tool(name="send_webhook_message", description="Send a message via webhook ID/token.")
    async def send_webhook_message(
        webhook_id: str,
        webhook_token: str,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        wait: bool = True,
    ) -> dict | None:
        return await runtime.send_webhook_message(
            webhook_id,
            webhook_token,
            content=content,
            username=username,
            avatar_url=avatar_url,
            embeds=embeds,
            wait=wait,
        )

    @mcp.tool(name="delete_webhook", description="Delete a webhook by ID.")
    async def delete_webhook(
        webhook_id: str,
        audit_log_reason: str | None = None,
    ) -> dict | None:
        return await runtime.delete_webhook(webhook_id, audit_log_reason=audit_log_reason)

    @mcp.tool(
        name="get_server_blueprint_schema",
        description="Return the supported JSON shape for apply_server_blueprint.",
    )
    def get_server_blueprint_schema() -> dict:
        return runtime.get_server_blueprint_schema()

    @mcp.tool(
        name="apply_server_blueprint",
        description=(
            "Create roles, categories, text channels, and voice channels inside an existing "
            "server. This does not create a new Discord server."
        ),
    )
    async def apply_server_blueprint(
        guild_id: str,
        blueprint: dict[str, Any],
        dry_run: bool = False,
    ) -> dict:
        return await runtime.apply_server_blueprint(guild_id, blueprint, dry_run=dry_run)

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
