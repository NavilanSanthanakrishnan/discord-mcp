from __future__ import annotations

import asyncio
import base64
import mimetypes
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from discord_user_mcp.config import Settings
from discord_user_mcp.discord.gateway import DiscordGatewayWatcher
from discord_user_mcp.discord.models import (
    DiscordChannel,
    DiscordGuild,
    DiscordMessage,
    DMChannel,
)
from discord_user_mcp.discord.rest import DiscordRestClient
from discord_user_mcp.storage.db import DiscordStore


class RestClientProtocol(Protocol):
    async def aclose(self) -> None: ...

    async def get_current_user(self) -> dict[str, Any]: ...

    async def get_user_settings(self) -> dict[str, Any]: ...

    async def set_custom_status(
        self,
        *,
        text: str | None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]: ...

    async def list_dm_channels(self) -> list[DMChannel]: ...

    async def list_guilds(self) -> list[DiscordGuild]: ...

    async def list_guild_channels(self, guild_id: str) -> list[DiscordChannel]: ...

    async def read_messages(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[DiscordMessage]: ...

    async def send_message(self, channel_id: str, content: str) -> DiscordMessage: ...

    async def reply_to_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage: ...

    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage: ...

    async def delete_message(self, channel_id: str, message_id: str) -> None: ...

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None: ...

    async def remove_own_reaction(self, channel_id: str, message_id: str, emoji: str) -> None: ...

    async def send_typing_indicator(self, channel_id: str) -> None: ...

    async def send_message_with_attachments(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        attachment_paths: list[str],
    ) -> DiscordMessage: ...

    async def request_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any | None] | None = None,
        json_body: Any | None = None,
        audit_log_reason: str | None = None,
    ) -> Any: ...


@dataclass
class DiscordUserMcpRuntime:
    settings: Settings
    token: str
    store: DiscordStore
    rest: RestClientProtocol
    watcher: DiscordGatewayWatcher
    gateway_task: asyncio.Task[None] | None = None
    gateway_enabled: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> DiscordUserMcpRuntime:
        token = settings.read_token()
        store = DiscordStore(settings.db_path)
        rest = DiscordRestClient(token, base_url=settings.discord_api_base)
        watcher = DiscordGatewayWatcher(token, store, gateway_url=settings.discord_gateway_url)
        return cls(settings=settings, token=token, store=store, rest=rest, watcher=watcher)

    async def start(self) -> None:
        if not self.gateway_enabled:
            return
        if self.gateway_task is None or self.gateway_task.done():
            self.gateway_task = asyncio.create_task(self.watcher.run_forever())

    async def wait_until_gateway_ready(self, *, timeout: float = 3) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.watcher.status.current_user_id or self.watcher.status.last_error:
                return
            await asyncio.sleep(0.1)

    async def close(self) -> None:
        self.watcher.stop()
        if self.gateway_task is not None:
            self.gateway_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.gateway_task
        await self.rest.aclose()
        self.store.close()

    async def status(self) -> dict[str, Any]:
        await self.start()
        await self.wait_until_gateway_ready(timeout=2)
        return {
            "connected": self.watcher.status.connected,
            "current_user_id": self.watcher.status.current_user_id,
            "known_dm_count": self.watcher.status.known_dm_count,
            "last_sequence": self.watcher.status.last_sequence,
            "last_event_type": self.watcher.status.last_event_type,
            "last_heartbeat_ack_at": self.watcher.status.last_heartbeat_ack_at.isoformat()
            if self.watcher.status.last_heartbeat_ack_at
            else None,
            "last_error": self.watcher.status.last_error,
            "token_loaded": bool(self.token),
            "db_path": str(self.settings.db_path),
            "allow_send": self.settings.allow_send,
        }

    async def get_custom_status(self) -> dict[str, Any]:
        await self.start()
        settings = await self.rest.get_user_settings()
        return {
            "status": settings.get("status"),
            "custom_status": settings.get("custom_status"),
        }

    async def set_custom_status(
        self,
        *,
        text: str | None = None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Custom status updates are disabled by ALLOW_SEND=false")
        if text is not None and not text.strip():
            text = None
        settings = await self.rest.set_custom_status(
            text=text,
            emoji_name=emoji_name,
            emoji_id=emoji_id,
            expires_at=expires_at,
        )
        return {
            "status": settings.get("status"),
            "custom_status": settings.get("custom_status"),
        }

    async def discord_api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any | None] | None = None,
        json_body: Any | None = None,
        audit_log_reason: str | None = None,
    ) -> Any:
        await self.start()
        return await self._api(
            method,
            path,
            params=params,
            json_body=json_body,
            audit_log_reason=audit_log_reason,
        )

    async def get_current_user(self) -> dict[str, Any]:
        await self.start()
        return await self.rest.get_current_user()

    async def get_bot_invite_url(
        self,
        *,
        permissions: str = "0",
        guild_id: str | None = None,
        scopes: str = "bot applications.commands",
    ) -> dict[str, Any]:
        current_user = await self.get_current_user()
        client_id = current_user["id"]
        query: dict[str, str] = {
            "client_id": client_id,
            "permissions": permissions,
            "scope": scopes,
        }
        if guild_id:
            query["guild_id"] = guild_id
            query["disable_guild_select"] = "true"
        return {
            "client_id": client_id,
            "url": "https://discord.com/oauth2/authorize?" + urlencode(query),
        }

    async def list_relationships(
        self,
        *,
        relationship_type: int | None = None,
    ) -> list[dict[str, Any]]:
        relationships = await self._api("GET", "users/@me/relationships")
        if relationship_type is None:
            return relationships
        return [
            relationship
            for relationship in relationships
            if relationship.get("type") == relationship_type
        ]

    async def list_message_requests(
        self,
        *,
        relationship_types: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        request_types = set(relationship_types or [3, 4])
        return [
            relationship
            for relationship in await self.list_relationships()
            if relationship.get("type") in request_types
        ]

    async def poll_message_requests(
        self,
        *,
        known_user_ids: list[str] | None = None,
        relationship_types: list[int] | None = None,
    ) -> dict[str, Any]:
        known = set(known_user_ids or [])
        requests = await self.list_message_requests(relationship_types=relationship_types)
        request_user_ids = [self._relationship_user_id(request) for request in requests]
        return {
            "request_user_ids": request_user_ids,
            "requests": requests,
            "new_requests": [
                request
                for request in requests
                if self._relationship_user_id(request) not in known
            ],
        }

    async def accept_message_request(self, user_id: str) -> dict[str, Any] | None:
        return await self._api(
            "PUT",
            f"users/@me/relationships/{user_id}",
            json_body={"confirm_stranger_request": True},
        )

    async def delete_relationship(self, user_id: str) -> dict[str, Any] | None:
        return await self._api("DELETE", f"users/@me/relationships/{user_id}")

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        return await self._api("GET", f"users/{user_id}/profile")

    async def ack_message(
        self,
        channel_id: str,
        message_id: str,
        *,
        last_viewed: int | None = None,
        ack_token: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "POST",
            f"channels/{channel_id}/messages/{message_id}/ack",
            json_body=self._compact_payload(
                {
                    "last_viewed": last_viewed,
                    "token": ack_token,
                }
            ),
        )

    async def refresh_dms(self) -> list[dict[str, Any]]:
        await self.start()
        channels = await self.rest.list_dm_channels()
        self.store.upsert_dm_channels(channels)
        return [self._dm_channel_to_dict(channel) for channel in channels]

    async def create_dm_channel(self, user_id: str) -> dict[str, Any]:
        return await self._api(
            "POST",
            "users/@me/channels",
            json_body={"recipient_id": user_id},
        )

    async def send_private_message(self, user_id: str, content: str) -> dict[str, Any]:
        channel = await self.create_dm_channel(user_id)
        return await self.send_message(channel["id"], content)

    async def read_private_messages(
        self,
        user_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        compact: bool = True,
    ) -> list[dict[str, Any]]:
        channel = await self.create_dm_channel(user_id)
        return await self.read_messages(
            channel["id"],
            limit=limit,
            before=before,
            after=after,
            around=around,
            compact=compact,
        )

    async def edit_private_message(
        self,
        user_id: str,
        message_id: str,
        content: str,
    ) -> dict[str, Any]:
        channel = await self.create_dm_channel(user_id)
        return await self.edit_dm_message(channel["id"], message_id, content)

    async def delete_private_message(self, user_id: str, message_id: str) -> dict[str, Any]:
        channel = await self.create_dm_channel(user_id)
        return await self.delete_dm_message(channel["id"], message_id)

    async def list_dms(
        self,
        *,
        limit: int = 50,
        query: str | None = None,
        refresh: bool = True,
    ) -> list[dict[str, Any]]:
        if refresh:
            channels = await self.refresh_dms()
        else:
            channels = self.store.list_dm_channels()

        if query:
            needle = query.casefold()
            channels = [
                channel
                for channel in channels
                if needle in channel["name"].casefold() or needle in channel["channel_id"]
            ]

        return sorted(
            channels,
            key=lambda channel: channel.get("last_message_id") or "0",
            reverse=True,
        )[:limit]

    async def list_servers(
        self,
        *,
        limit: int = 100,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.start()
        guilds = [self._guild_to_dict(guild) for guild in await self.rest.list_guilds()]
        if query:
            needle = query.casefold()
            guilds = [
                guild
                for guild in guilds
                if needle in guild["name"].casefold() or needle in guild["guild_id"]
            ]
        return sorted(guilds, key=lambda guild: guild["name"].casefold())[:limit]

    async def list_server_channels(
        self,
        guild_id: str,
        *,
        limit: int = 100,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.start()
        channels = [
            self._server_channel_to_dict(channel)
            for channel in await self.rest.list_guild_channels(guild_id)
        ]
        if query:
            needle = query.casefold()
            channels = [
                channel
                for channel in channels
                if needle in channel["name"].casefold() or needle in channel["channel_id"]
            ]
        return sorted(
            channels,
            key=lambda channel: (
                channel["position"] if channel["position"] is not None else 999999,
                channel["name"].casefold(),
            ),
        )[:limit]

    async def get_server_info(self, guild_id: str, *, with_counts: bool = True) -> dict[str, Any]:
        await self.start()
        return await self._api(
            "GET",
            f"guilds/{guild_id}",
            params={"with_counts": str(with_counts).lower()},
        )

    async def list_all_server_channels(self, guild_id: str) -> list[dict[str, Any]]:
        await self.start()
        return await self._api("GET", f"guilds/{guild_id}/channels")

    async def list_active_threads(self, guild_id: str) -> dict[str, Any]:
        await self.start()
        return await self._api("GET", f"guilds/{guild_id}/threads/active")

    async def create_server(
        self,
        name: str,
        *,
        template_code: str | None = None,
        icon: str | None = None,
    ) -> dict[str, Any]:
        if not template_code:
            raise RuntimeError(
                "Discord's supported API path creates servers from a guild template. "
                "Pass template_code, or create an empty server manually and use "
                "apply_server_blueprint inside it."
            )
        return await self.create_server_from_template(template_code, name=name, icon=icon)

    async def create_server_from_template(
        self,
        template_code: str,
        *,
        name: str,
        icon: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"guilds/templates/{self._template_code(template_code)}",
            json_body=self._compact_payload({"name": name, "icon": icon}),
        )

    async def get_server_preview(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/preview")

    async def list_server_voice_regions(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/regions")

    async def get_server_vanity_url(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/vanity-url")

    async def get_server_widget(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/widget")

    async def get_server_widget_json(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/widget.json")

    async def edit_server_widget(
        self,
        guild_id: str,
        *,
        enabled: bool,
        channel_id: str | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/widget",
            json_body={"enabled": enabled, "channel_id": channel_id},
            audit_log_reason=audit_log_reason,
        )

    async def get_welcome_screen(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/welcome-screen")

    async def edit_welcome_screen(
        self,
        guild_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one welcome screen field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/welcome-screen",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def get_server_onboarding(self, guild_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/onboarding")

    async def edit_server_onboarding(
        self,
        guild_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one onboarding field")
        return await self._api(
            "PUT",
            f"guilds/{guild_id}/onboarding",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def leave_server(
        self,
        guild_id: str,
        *,
        confirm_server_name: str,
    ) -> dict[str, Any] | None:
        server = await self.get_server_info(guild_id, with_counts=False)
        actual_name = server.get("name")
        if actual_name != confirm_server_name:
            raise ValueError("confirm_server_name must exactly match the server name")
        return await self._api("DELETE", f"users/@me/guilds/{guild_id}")

    async def edit_server_settings(
        self,
        guild_id: str,
        settings: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not settings:
            raise ValueError("settings must include at least one Discord guild field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}",
            json_body=self._compact_payload(settings),
            audit_log_reason=audit_log_reason,
        )

    async def get_audit_log(
        self,
        guild_id: str,
        *,
        user_id: str | None = None,
        action_type: int | None = None,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/audit-logs",
            params={
                "user_id": user_id,
                "action_type": action_type,
                "before": before,
                "limit": limit,
            },
        )

    async def create_text_channel(
        self,
        guild_id: str,
        name: str,
        *,
        topic: str | None = None,
        parent_id: str | None = None,
        nsfw: bool | None = None,
        rate_limit_per_user: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._create_guild_channel(
            guild_id,
            {
                "name": name,
                "type": 0,
                "topic": topic,
                "parent_id": parent_id,
                "nsfw": nsfw,
                "rate_limit_per_user": rate_limit_per_user,
                "position": position,
            },
            audit_log_reason=audit_log_reason,
        )

    async def create_voice_channel(
        self,
        guild_id: str,
        name: str,
        *,
        parent_id: str | None = None,
        bitrate: int | None = None,
        user_limit: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._create_guild_channel(
            guild_id,
            {
                "name": name,
                "type": 2,
                "parent_id": parent_id,
                "bitrate": bitrate,
                "user_limit": user_limit,
                "position": position,
            },
            audit_log_reason=audit_log_reason,
        )

    async def create_stage_channel(
        self,
        guild_id: str,
        name: str,
        *,
        parent_id: str | None = None,
        bitrate: int | None = None,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._create_guild_channel(
            guild_id,
            {
                "name": name,
                "type": 13,
                "parent_id": parent_id,
                "bitrate": bitrate,
                "position": position,
            },
            audit_log_reason=audit_log_reason,
        )

    async def create_category(
        self,
        guild_id: str,
        name: str,
        *,
        position: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._create_guild_channel(
            guild_id,
            {"name": name, "type": 4, "position": position},
            audit_log_reason=audit_log_reason,
        )

    async def create_forum_channel(
        self,
        guild_id: str,
        name: str,
        *,
        topic: str | None = None,
        parent_id: str | None = None,
        nsfw: bool | None = None,
        rate_limit_per_user: int | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._create_guild_channel(
            guild_id,
            {
                "name": name,
                "type": 15,
                "topic": topic,
                "parent_id": parent_id,
                "nsfw": nsfw,
                "rate_limit_per_user": rate_limit_per_user,
            },
            audit_log_reason=audit_log_reason,
        )

    async def edit_forum_channel(
        self,
        channel_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self.edit_channel(
            channel_id,
            fields,
            audit_log_reason=audit_log_reason,
        )

    async def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        return await self._api("GET", f"channels/{channel_id}")

    async def find_channel(
        self,
        guild_id: str,
        query: str,
        *,
        channel_type: int | None = None,
    ) -> list[dict[str, Any]]:
        needle = query.casefold()
        channels = await self.list_all_server_channels(guild_id)
        return [
            channel
            for channel in channels
            if needle in channel.get("name", "").casefold()
            and (channel_type is None or channel.get("type") == channel_type)
        ]

    async def list_channels_in_category(
        self,
        guild_id: str,
        category_id: str,
    ) -> list[dict[str, Any]]:
        channels = await self.list_all_server_channels(guild_id)
        return [channel for channel in channels if channel.get("parent_id") == category_id]

    async def move_channel(
        self,
        guild_id: str,
        channel_id: str,
        *,
        position: int | None = None,
        parent_id: str | None = None,
        lock_permissions: bool | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        payload = self._compact_payload(
            {
                "id": channel_id,
                "position": position,
                "parent_id": parent_id,
                "lock_permissions": lock_permissions,
            }
        )
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/channels",
            json_body=[payload],
            audit_log_reason=audit_log_reason,
        )

    async def list_channel_permission_overwrites(
        self,
        channel_id: str,
    ) -> list[dict[str, Any]]:
        channel = await self.get_channel_info(channel_id)
        return channel.get("permission_overwrites", [])

    async def upsert_channel_permission_overwrite(
        self,
        channel_id: str,
        overwrite_id: str,
        *,
        overwrite_type: int,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "PUT",
            f"channels/{channel_id}/permissions/{overwrite_id}",
            json_body={"type": overwrite_type, "allow": allow, "deny": deny},
            audit_log_reason=audit_log_reason,
        )

    async def upsert_role_channel_permissions(
        self,
        channel_id: str,
        role_id: str,
        *,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.upsert_channel_permission_overwrite(
            channel_id,
            role_id,
            overwrite_type=0,
            allow=allow,
            deny=deny,
            audit_log_reason=audit_log_reason,
        )

    async def upsert_member_channel_permissions(
        self,
        channel_id: str,
        user_id: str,
        *,
        allow: str = "0",
        deny: str = "0",
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.upsert_channel_permission_overwrite(
            channel_id,
            user_id,
            overwrite_type=1,
            allow=allow,
            deny=deny,
            audit_log_reason=audit_log_reason,
        )

    async def delete_channel_permission_overwrite(
        self,
        channel_id: str,
        overwrite_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"channels/{channel_id}/permissions/{overwrite_id}",
            audit_log_reason=audit_log_reason,
        )

    async def list_forum_channels(self, guild_id: str) -> list[dict[str, Any]]:
        channels = await self.list_all_server_channels(guild_id)
        return [channel for channel in channels if channel.get("type") in {15, 16}]

    async def get_forum_channel_info(self, forum_channel_id: str) -> dict[str, Any]:
        return await self.get_channel_info(forum_channel_id)

    async def list_forum_tags(self, forum_channel_id: str) -> list[dict[str, Any]]:
        forum = await self.get_forum_channel_info(forum_channel_id)
        return forum.get("available_tags", [])

    async def create_forum_post(
        self,
        forum_channel_id: str,
        *,
        name: str,
        content: str,
        applied_tags: list[str] | None = None,
        embeds: list[dict[str, Any]] | None = None,
        auto_archive_duration: int | None = None,
        rate_limit_per_user: int | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"channels/{forum_channel_id}/threads",
            json_body=self._compact_payload(
                {
                    "name": name,
                    "applied_tags": applied_tags,
                    "auto_archive_duration": auto_archive_duration,
                    "rate_limit_per_user": rate_limit_per_user,
                    "message": self._compact_payload({"content": content, "embeds": embeds}),
                }
            ),
        )

    async def list_forum_posts(
        self,
        forum_channel_id: str,
        *,
        guild_id: str | None = None,
        include_archived: bool = True,
    ) -> dict[str, Any]:
        active: list[dict[str, Any]] = []
        if guild_id:
            active_payload = await self.list_active_threads(guild_id)
            active = [
                thread
                for thread in active_payload.get("threads", [])
                if thread.get("parent_id") == forum_channel_id
            ]

        archived_public = None
        if include_archived:
            archived_public = await self._api(
                "GET",
                f"channels/{forum_channel_id}/threads/archived/public",
            )
        return {"active": active, "archived_public": archived_public}

    async def modify_forum_post(
        self,
        thread_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one forum post/thread field")
        return await self._api(
            "PATCH",
            f"channels/{thread_id}",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def edit_channel(
        self,
        channel_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one channel field")
        return await self._api(
            "PATCH",
            f"channels/{channel_id}",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def delete_channel(
        self,
        channel_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "DELETE",
            f"channels/{channel_id}",
            audit_log_reason=audit_log_reason,
        )

    async def pin_message(
        self,
        channel_id: str,
        message_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "PUT",
            f"channels/{channel_id}/pins/{message_id}",
            audit_log_reason=audit_log_reason,
        )

    async def unpin_message(
        self,
        channel_id: str,
        message_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"channels/{channel_id}/pins/{message_id}",
            audit_log_reason=audit_log_reason,
        )

    async def bulk_delete_messages(
        self,
        channel_id: str,
        message_ids: list[str],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if not 2 <= len(message_ids) <= 100:
            raise ValueError("message_ids must contain between 2 and 100 message IDs")
        return await self._api(
            "POST",
            f"channels/{channel_id}/messages/bulk-delete",
            json_body={"messages": message_ids},
            audit_log_reason=audit_log_reason,
        )

    async def crosspost_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        return await self._api("POST", f"channels/{channel_id}/messages/{message_id}/crosspost")

    async def get_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        return await self._api("GET", f"channels/{channel_id}/messages/{message_id}")

    async def get_attachment(
        self,
        channel_id: str,
        message_id: str,
        attachment_id: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        message = await self.get_message(channel_id, message_id)
        attachments = message.get("attachments", [])
        if attachment_id is None:
            return attachments
        for attachment in attachments:
            if attachment.get("id") == attachment_id:
                return attachment
        raise ValueError("attachment_id was not found on the message")

    async def list_roles(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/roles")

    async def create_role(
        self,
        guild_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"guilds/{guild_id}/roles",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def edit_role(
        self,
        guild_id: str,
        role_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one role field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/roles/{role_id}",
            json_body=self._compact_payload(fields),
            audit_log_reason=audit_log_reason,
        )

    async def delete_role(
        self,
        guild_id: str,
        role_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/roles/{role_id}",
            audit_log_reason=audit_log_reason,
        )

    async def assign_role(
        self,
        guild_id: str,
        user_id: str,
        role_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "PUT",
            f"guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            audit_log_reason=audit_log_reason,
        )

    async def remove_role(
        self,
        guild_id: str,
        user_id: str,
        role_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            audit_log_reason=audit_log_reason,
        )

    async def get_member(self, guild_id: str, user_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/members/{user_id}")

    async def list_members(
        self,
        guild_id: str,
        *,
        limit: int = 100,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/members",
            params={"limit": limit, "after": after},
        )

    async def search_members(
        self,
        guild_id: str,
        query: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/members/search",
            params={"query": query, "limit": limit},
        )

    async def get_user_id_by_name(
        self,
        guild_id: str,
        username: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        members = await self.search_members(guild_id, username, limit=limit)
        needle = username.casefold()
        matches = []
        for member in members:
            user = member.get("user", {})
            names = [
                user.get("username"),
                user.get("global_name"),
                member.get("nick"),
            ]
            if any(isinstance(name, str) and needle in name.casefold() for name in names):
                matches.append(
                    {
                        "user_id": user.get("id"),
                        "username": user.get("username"),
                        "global_name": user.get("global_name"),
                        "nick": member.get("nick"),
                        "member": member,
                    }
                )
        return matches

    async def add_member_to_server(
        self,
        guild_id: str,
        user_id: str,
        *,
        access_token: str,
        nick: str | None = None,
        roles: list[str] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "PUT",
            f"guilds/{guild_id}/members/{user_id}",
            json_body=self._compact_payload(
                {
                    "access_token": access_token,
                    "nick": nick,
                    "roles": roles,
                    "mute": mute,
                    "deaf": deaf,
                }
            ),
        )

    async def list_member_roles(self, guild_id: str, user_id: str) -> list[str]:
        member = await self.get_member(guild_id, user_id)
        return member.get("roles", [])

    async def modify_member(
        self,
        guild_id: str,
        user_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if not fields:
            raise ValueError("fields must include at least one member field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/members/{user_id}",
            json_body=fields,
            audit_log_reason=audit_log_reason,
        )

    async def set_nickname(
        self,
        guild_id: str,
        user_id: str,
        *,
        nick: str | None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.modify_member(
            guild_id,
            user_id,
            {"nick": nick},
            audit_log_reason=audit_log_reason,
        )

    async def move_member(
        self,
        guild_id: str,
        user_id: str,
        channel_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.modify_member(
            guild_id,
            user_id,
            {"channel_id": channel_id},
            audit_log_reason=audit_log_reason,
        )

    async def disconnect_member(
        self,
        guild_id: str,
        user_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.modify_member(
            guild_id,
            user_id,
            {"channel_id": None},
            audit_log_reason=audit_log_reason,
        )

    async def modify_voice_state(
        self,
        guild_id: str,
        user_id: str,
        *,
        mute: bool | None = None,
        deaf: bool | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if mute is None and deaf is None:
            raise ValueError("mute or deaf must be provided")
        return await self.modify_member(
            guild_id,
            user_id,
            self._compact_payload({"mute": mute, "deaf": deaf}),
            audit_log_reason=audit_log_reason,
        )

    async def timeout_member(
        self,
        guild_id: str,
        user_id: str,
        *,
        duration_seconds: int,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if duration_seconds <= 0 or duration_seconds > 2_419_200:
            raise ValueError("duration_seconds must be between 1 and 2419200")
        until = datetime.now(UTC) + timedelta(seconds=duration_seconds)
        return await self.modify_member(
            guild_id,
            user_id,
            {"communication_disabled_until": until.isoformat().replace("+00:00", "Z")},
            audit_log_reason=audit_log_reason,
        )

    async def remove_timeout(
        self,
        guild_id: str,
        user_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.modify_member(
            guild_id,
            user_id,
            {"communication_disabled_until": None},
            audit_log_reason=audit_log_reason,
        )

    async def kick_member(
        self,
        guild_id: str,
        user_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/members/{user_id}",
            audit_log_reason=audit_log_reason,
        )

    async def ban_member(
        self,
        guild_id: str,
        user_id: str,
        *,
        delete_message_seconds: int = 0,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if delete_message_seconds < 0 or delete_message_seconds > 604_800:
            raise ValueError("delete_message_seconds must be between 0 and 604800")
        return await self._api(
            "PUT",
            f"guilds/{guild_id}/bans/{user_id}",
            json_body={"delete_message_seconds": delete_message_seconds},
            audit_log_reason=audit_log_reason,
        )

    async def unban_member(
        self,
        guild_id: str,
        user_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/bans/{user_id}",
            audit_log_reason=audit_log_reason,
        )

    async def list_bans(
        self,
        guild_id: str,
        *,
        limit: int = 1000,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/bans",
            params={"limit": limit, "before": before, "after": after},
        )

    async def list_guild_scheduled_events(
        self,
        guild_id: str,
        *,
        with_user_count: bool = True,
    ) -> list[dict[str, Any]]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/scheduled-events",
            params={"with_user_count": str(with_user_count).lower()},
        )

    async def create_guild_scheduled_event(
        self,
        guild_id: str,
        *,
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
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"guilds/{guild_id}/scheduled-events",
            json_body=self._compact_payload(
                {
                    "name": name,
                    "scheduled_start_time": scheduled_start_time,
                    "entity_type": entity_type,
                    "channel_id": channel_id,
                    "scheduled_end_time": scheduled_end_time,
                    "description": description,
                    "entity_metadata": entity_metadata,
                    "privacy_level": privacy_level,
                    "image": image,
                    "recurrence_rule": recurrence_rule,
                }
            ),
            audit_log_reason=audit_log_reason,
        )

    async def get_guild_scheduled_event(
        self,
        guild_id: str,
        event_id: str,
        *,
        with_user_count: bool = True,
    ) -> dict[str, Any]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/scheduled-events/{event_id}",
            params={"with_user_count": str(with_user_count).lower()},
        )

    async def edit_guild_scheduled_event(
        self,
        guild_id: str,
        event_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one scheduled event field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/scheduled-events/{event_id}",
            json_body=fields,
            audit_log_reason=audit_log_reason,
        )

    async def delete_guild_scheduled_event(
        self,
        guild_id: str,
        event_id: str,
    ) -> dict[str, Any] | None:
        return await self._api("DELETE", f"guilds/{guild_id}/scheduled-events/{event_id}")

    async def get_guild_scheduled_event_users(
        self,
        guild_id: str,
        event_id: str,
        *,
        limit: int = 100,
        with_member: bool = False,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._api(
            "GET",
            f"guilds/{guild_id}/scheduled-events/{event_id}/users",
            params={
                "limit": limit,
                "with_member": str(with_member).lower(),
                "before": before,
                "after": after,
            },
        )

    async def create_invite(
        self,
        channel_id: str,
        *,
        max_age: int = 86400,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = False,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"channels/{channel_id}/invites",
            json_body={
                "max_age": max_age,
                "max_uses": max_uses,
                "temporary": temporary,
                "unique": unique,
            },
            audit_log_reason=audit_log_reason,
        )

    async def get_invite(self, invite_code: str, *, with_counts: bool = True) -> dict[str, Any]:
        return await self._api(
            "GET",
            f"invites/{self._invite_code(invite_code)}",
            params={"with_counts": str(with_counts).lower()},
        )

    async def list_invites(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/invites")

    async def delete_invite(
        self,
        invite_code: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "DELETE",
            f"invites/{self._invite_code(invite_code)}",
            audit_log_reason=audit_log_reason,
        )

    async def list_guild_templates(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/templates")

    async def get_guild_template(self, template_code: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/templates/{self._template_code(template_code)}")

    async def create_guild_template(
        self,
        guild_id: str,
        name: str,
        *,
        description: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"guilds/{guild_id}/templates",
            json_body=self._compact_payload({"name": name, "description": description}),
        )

    async def sync_guild_template(self, guild_id: str, template_code: str) -> dict[str, Any]:
        return await self._api(
            "PUT",
            f"guilds/{guild_id}/templates/{self._template_code(template_code)}",
        )

    async def edit_guild_template(
        self,
        guild_id: str,
        template_code: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one template field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/templates/{self._template_code(template_code)}",
            json_body=self._compact_payload(fields),
        )

    async def delete_guild_template(self, guild_id: str, template_code: str) -> dict[str, Any]:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/templates/{self._template_code(template_code)}",
        )

    async def list_emojis(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/emojis")

    async def get_emoji(self, guild_id: str, emoji_id: str) -> dict[str, Any]:
        return await self._api("GET", f"guilds/{guild_id}/emojis/{emoji_id}")

    async def create_emoji(
        self,
        guild_id: str,
        *,
        name: str,
        image: str | None = None,
        image_path: str | None = None,
        roles: list[str] | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        image_data = image or self._image_data_uri(image_path)
        return await self._api(
            "POST",
            f"guilds/{guild_id}/emojis",
            json_body=self._compact_payload(
                {
                    "name": name,
                    "image": image_data,
                    "roles": roles,
                }
            ),
            audit_log_reason=audit_log_reason,
        )

    async def edit_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        fields: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not fields:
            raise ValueError("fields must include at least one emoji field")
        return await self._api(
            "PATCH",
            f"guilds/{guild_id}/emojis/{emoji_id}",
            json_body=fields,
            audit_log_reason=audit_log_reason,
        )

    async def delete_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"guilds/{guild_id}/emojis/{emoji_id}",
            audit_log_reason=audit_log_reason,
        )

    async def create_webhook(
        self,
        channel_id: str,
        name: str,
        *,
        avatar: str | None = None,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        return await self._api(
            "POST",
            f"channels/{channel_id}/webhooks",
            json_body=self._compact_payload({"name": name, "avatar": avatar}),
            audit_log_reason=audit_log_reason,
        )

    async def list_channel_webhooks(self, channel_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"channels/{channel_id}/webhooks")

    async def list_guild_webhooks(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._api("GET", f"guilds/{guild_id}/webhooks")

    async def list_webhooks(self, channel_id: str) -> list[dict[str, Any]]:
        return await self.list_channel_webhooks(channel_id)

    async def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        return await self._api("GET", f"webhooks/{webhook_id}")

    async def send_webhook_message(
        self,
        webhook_id: str,
        webhook_token: str,
        *,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        wait: bool = True,
    ) -> dict[str, Any] | None:
        payload = self._compact_payload(
            {
                "content": content,
                "username": username,
                "avatar_url": avatar_url,
                "embeds": embeds,
            }
        )
        if not payload:
            raise ValueError(
                "content, embeds, username/avatar_url with content, "
                "or another body field is required"
            )
        return await self._api(
            "POST",
            f"webhooks/{webhook_id}/{webhook_token}",
            params={"wait": str(wait).lower()},
            json_body=payload,
        )

    async def delete_webhook(
        self,
        webhook_id: str,
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._api(
            "DELETE",
            f"webhooks/{webhook_id}",
            audit_log_reason=audit_log_reason,
        )

    async def apply_server_blueprint(
        self,
        guild_id: str,
        blueprint: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        category_ids_by_name: dict[str, str] = {}

        for role in blueprint.get("roles", []):
            name = self._required_name(role)
            if dry_run:
                actions.append({"action": "create_role", "name": name})
            else:
                created = await self.create_role(guild_id, role)
                actions.append({"action": "create_role", "result": created})

        for category in blueprint.get("categories", []):
            name = self._required_name(category)
            if dry_run:
                actions.append({"action": "create_category", "name": name})
                parent_id = None
            else:
                created_category = await self.create_category(guild_id, name)
                parent_id = created_category["id"]
                category_ids_by_name[name] = parent_id
                actions.append({"action": "create_category", "result": created_category})

            for channel in category.get("text_channels", []):
                action = await self._blueprint_text_channel(
                    guild_id,
                    channel,
                    parent_id=parent_id,
                    dry_run=dry_run,
                )
                actions.append(action)
            for channel in category.get("voice_channels", []):
                action = await self._blueprint_voice_channel(
                    guild_id,
                    channel,
                    parent_id=parent_id,
                    dry_run=dry_run,
                )
                actions.append(action)

        for channel in blueprint.get("text_channels", []):
            parent_id = self._blueprint_parent_id(channel, category_ids_by_name)
            actions.append(
                await self._blueprint_text_channel(
                    guild_id,
                    channel,
                    parent_id=parent_id,
                    dry_run=dry_run,
                )
            )

        for channel in blueprint.get("voice_channels", []):
            parent_id = self._blueprint_parent_id(channel, category_ids_by_name)
            actions.append(
                await self._blueprint_voice_channel(
                    guild_id,
                    channel,
                    parent_id=parent_id,
                    dry_run=dry_run,
                )
            )

        return {"dry_run": dry_run, "actions": actions}

    @staticmethod
    def get_server_blueprint_schema() -> dict[str, Any]:
        return {
            "roles": [
                {
                    "name": "Admin",
                    "permissions": "8",
                    "color": 16711680,
                    "hoist": True,
                    "mentionable": False,
                }
            ],
            "categories": [
                {
                    "name": "Information",
                    "text_channels": [{"name": "rules", "topic": "Read first"}],
                    "voice_channels": [{"name": "Lobby", "user_limit": 0, "bitrate": 64000}],
                }
            ],
            "text_channels": [{"name": "general", "category_name": "Information"}],
            "voice_channels": [{"name": "General Voice", "category_name": "Information"}],
        }

    async def read_dm(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.start()
        messages = await self.rest.read_messages(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )
        for message in messages:
            self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return [self._message_to_dict(message) for message in messages]

    async def read_messages(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
        compact: bool = True,
    ) -> list[dict[str, Any]]:
        messages = await self.read_dm(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )
        if compact:
            return [self._compact_message_dict(message) for message in messages]
        return messages

    async def send_dm(self, channel_id: str, content: str) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Sending is disabled by ALLOW_SEND=false")
        message = await self.rest.send_message(channel_id, content)
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return self._message_to_dict(message)

    async def send_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return await self.send_dm(channel_id, content)

    async def send_channel_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return await self.send_dm(channel_id, content)

    async def read_channel_messages(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.read_dm(
            channel_id,
            limit=limit,
            before=before,
            after=after,
            around=around,
        )

    async def reply_to_dm_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Sending is disabled by ALLOW_SEND=false")
        message = await self.rest.reply_to_message(channel_id, message_id, content)
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return self._message_to_dict(message)

    async def reply_to_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> dict[str, Any]:
        return await self.reply_to_dm_message(channel_id, message_id, content)

    async def reply_to_channel_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> dict[str, Any]:
        return await self.reply_to_dm_message(channel_id, message_id, content)

    async def edit_dm_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Editing is disabled by ALLOW_SEND=false")
        message = await self.rest.edit_message(channel_id, message_id, content)
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return self._message_to_dict(message)

    async def delete_dm_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Deleting is disabled by ALLOW_SEND=false")
        await self.rest.delete_message(channel_id, message_id)
        return {"deleted": True, "channel_id": channel_id, "message_id": message_id}

    async def delete_message(self, channel_id: str, message_id: str) -> dict[str, Any]:
        return await self.delete_dm_message(channel_id, message_id)

    async def add_dm_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Reactions are disabled by ALLOW_SEND=false")
        await self.rest.add_reaction(channel_id, message_id, emoji)
        return {
            "reacted": True,
            "channel_id": channel_id,
            "message_id": message_id,
            "emoji": emoji,
        }

    async def add_message_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        return await self.add_dm_reaction(channel_id, message_id, emoji)

    async def remove_dm_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Reactions are disabled by ALLOW_SEND=false")
        await self.rest.remove_own_reaction(channel_id, message_id, emoji)
        return {
            "removed": True,
            "channel_id": channel_id,
            "message_id": message_id,
            "emoji": emoji,
        }

    async def remove_message_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        return await self.remove_dm_reaction(channel_id, message_id, emoji)

    async def send_typing_indicator(self, channel_id: str) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Typing indicators are disabled by ALLOW_SEND=false")
        await self.rest.send_typing_indicator(channel_id)
        return {"typing": True, "channel_id": channel_id}

    async def send_dm_attachments(
        self,
        channel_id: str,
        *,
        attachment_paths: list[str],
        content: str | None = None,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Sending is disabled by ALLOW_SEND=false")
        message = await self.rest.send_message_with_attachments(
            channel_id,
            content=content,
            attachment_paths=attachment_paths,
        )
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return self._message_to_dict(message)

    async def send_attachments(
        self,
        channel_id: str,
        *,
        attachment_paths: list[str],
        content: str | None = None,
    ) -> dict[str, Any]:
        return await self.send_dm_attachments(
            channel_id,
            attachment_paths=attachment_paths,
            content=content,
        )

    async def send_natural_dm(
        self,
        channel_id: str,
        content: str,
        *,
        wpm: int | None = None,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> dict[str, Any]:
        await self.start()
        if not self.settings.allow_send:
            raise RuntimeError("Sending is disabled by ALLOW_SEND=false")

        typing_seconds = self.estimate_typing_seconds(
            content,
            wpm=wpm or self.settings.natural_typing_wpm,
            min_seconds=(
                self.settings.natural_typing_min_seconds
                if min_seconds is None
                else min_seconds
            ),
            max_seconds=(
                self.settings.natural_typing_max_seconds
                if max_seconds is None
                else max_seconds
            ),
        )
        await self._simulate_typing(channel_id, typing_seconds)
        message = await self.rest.send_message(channel_id, content)
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        result = self._message_to_dict(message)
        result["typing_seconds"] = typing_seconds
        return result

    async def send_natural_message(
        self,
        channel_id: str,
        content: str,
        *,
        wpm: int | None = None,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> dict[str, Any]:
        return await self.send_natural_dm(
            channel_id,
            content,
            wpm=wpm,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )

    async def poll_new_dm_events(
        self,
        *,
        after_event_id: int = 0,
        limit: int = 20,
        channel_id: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.start()
        return self.store.list_events(
            after_event_id=after_event_id,
            channel_id=channel_id,
            limit=limit,
        )

    def start_dm_watch(
        self,
        channel_id: str,
        *,
        context_limit: int = 30,
        idle_timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        self.store.set_active_watch(
            channel_id,
            context_limit=context_limit,
            idle_timeout_seconds=idle_timeout_seconds,
        )
        return {
            "active": True,
            "channel_id": channel_id,
            "context_limit": context_limit,
            "idle_timeout_seconds": idle_timeout_seconds,
        }

    def stop_dm_watch(self) -> dict[str, Any]:
        self.store.clear_active_watch()
        return {"active": False}

    async def poll_active_dm(
        self,
        *,
        wait_seconds: float = 0,
        max_events: int = 10,
    ) -> dict[str, Any]:
        await self.start()
        active = self.store.get_active_watch()
        if active is None:
            return {"active": False, "events": []}
        if self.store.active_watch_is_idle_expired():
            self.store.clear_active_watch()
            return {"active": False, "events": [], "idle_timeout": True}

        deadline = asyncio.get_running_loop().time() + max(0, wait_seconds)
        events: list[dict[str, Any]] = []
        while True:
            events = self.store.list_events(
                after_event_id=active["last_event_id"],
                channel_id=active["channel_id"],
                limit=max_events,
            )
            if events or wait_seconds <= 0 or asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(0.25)

        if events:
            self.store.update_active_watch_last_event(events[-1]["event_id"])

        return {"active": True, **active, "events": events}

    async def collect_dm_burst(
        self,
        channel_id: str,
        *,
        after_event_id: int = 0,
        quiet_seconds: float = 5,
        max_wait_seconds: float = 30,
        max_events: int = 20,
        respect_typing: bool = True,
        typing_ttl_seconds: float = 8,
    ) -> dict[str, Any]:
        await self.start()
        if quiet_seconds < 0 or max_wait_seconds < 0 or typing_ttl_seconds < 0:
            raise ValueError("timing values must be non-negative")
        if max_events < 1:
            raise ValueError("max_events must be at least 1")

        loop = asyncio.get_running_loop()
        started_at = loop.time()
        deadline = started_at + max_wait_seconds
        cursor = after_event_id
        message_events: list[dict[str, Any]] = []
        last_activity_at: float | None = None
        typing_active_until = 0.0
        typing_observed = False
        ended_reason = "max_wait"

        while True:
            new_events = self.store.list_events(
                after_event_id=cursor,
                channel_id=channel_id,
                limit=max_events,
            )
            if new_events:
                cursor = new_events[-1]["event_id"]

            for event in new_events:
                if event["event_type"] == "dm_message_create":
                    message_events.append(event)
                    last_activity_at = loop.time()
                elif event["event_type"] == "dm_typing_start" and respect_typing:
                    typing_observed = True
                    last_activity_at = loop.time()
                    typing_active_until = max(typing_active_until, loop.time() + typing_ttl_seconds)

            now = loop.time()
            if len(message_events) >= max_events:
                ended_reason = "max_events"
                break
            if message_events and last_activity_at is not None:
                quiet_deadline = last_activity_at + quiet_seconds
                if respect_typing:
                    quiet_deadline = max(quiet_deadline, typing_active_until)
                if now >= quiet_deadline:
                    ended_reason = "quiet_period"
                    break
            if now >= deadline:
                ended_reason = "max_wait"
                break

            await asyncio.sleep(min(0.25, max(0, deadline - now)))

        return {
            "channel_id": channel_id,
            "events": message_events[:max_events],
            "last_event_id": cursor,
            "ended_reason": ended_reason,
            "typing_observed": typing_observed,
        }

    async def _api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any | None] | None = None,
        json_body: Any | None = None,
        audit_log_reason: str | None = None,
    ) -> Any:
        method = method.upper().strip()
        if method in {"POST", "PUT", "PATCH", "DELETE"} and not self.settings.allow_send:
            raise RuntimeError("Discord write operations are disabled by ALLOW_SEND=false")
        return await self.rest.request_api(
            method,
            path,
            params=params,
            json_body=json_body,
            audit_log_reason=audit_log_reason,
        )

    async def _create_guild_channel(
        self,
        guild_id: str,
        payload: dict[str, Any],
        *,
        audit_log_reason: str | None = None,
    ) -> dict[str, Any]:
        if not payload.get("name"):
            raise ValueError("name must not be blank")
        return await self._api(
            "POST",
            f"guilds/{guild_id}/channels",
            json_body=self._compact_payload(payload),
            audit_log_reason=audit_log_reason,
        )

    async def _blueprint_text_channel(
        self,
        guild_id: str,
        channel: dict[str, Any],
        *,
        parent_id: str | None,
        dry_run: bool,
    ) -> dict[str, Any]:
        name = self._required_name(channel)
        if dry_run:
            return {"action": "create_text_channel", "name": name, "parent_id": parent_id}
        created = await self.create_text_channel(
            guild_id,
            name,
            parent_id=parent_id,
            topic=channel.get("topic"),
            nsfw=channel.get("nsfw"),
            rate_limit_per_user=channel.get("rate_limit_per_user", channel.get("slowmode")),
            position=channel.get("position"),
        )
        return {"action": "create_text_channel", "result": created}

    async def _blueprint_voice_channel(
        self,
        guild_id: str,
        channel: dict[str, Any],
        *,
        parent_id: str | None,
        dry_run: bool,
    ) -> dict[str, Any]:
        name = self._required_name(channel)
        if dry_run:
            return {"action": "create_voice_channel", "name": name, "parent_id": parent_id}
        created = await self.create_voice_channel(
            guild_id,
            name,
            parent_id=parent_id,
            bitrate=channel.get("bitrate"),
            user_limit=channel.get("user_limit"),
            position=channel.get("position"),
        )
        return {"action": "create_voice_channel", "result": created}

    def _blueprint_parent_id(
        self,
        channel: dict[str, Any],
        category_ids_by_name: dict[str, str],
    ) -> str | None:
        if channel.get("parent_id"):
            return channel["parent_id"]
        if channel.get("category_id"):
            return channel["category_id"]
        if channel.get("category_name"):
            return category_ids_by_name.get(channel["category_name"])
        return None

    @staticmethod
    def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _required_name(payload: dict[str, Any]) -> str:
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("blueprint resources must include a non-blank name")
        return name

    @staticmethod
    def _relationship_user_id(relationship: dict[str, Any]) -> str | None:
        user = relationship.get("user")
        if isinstance(user, dict):
            return user.get("id")
        return relationship.get("id") or relationship.get("user_id")

    @staticmethod
    def _image_data_uri(image_path: str | None) -> str:
        if not image_path:
            raise ValueError("image or image_path is required")
        path = Path(image_path).expanduser()
        content_type = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{content_type};base64,{data}"

    @staticmethod
    def _invite_code(invite_code_or_url: str) -> str:
        code = invite_code_or_url.strip()
        for prefix in (
            "https://discord.gg/",
            "http://discord.gg/",
            "https://discord.com/invite/",
            "http://discord.com/invite/",
        ):
            if code.startswith(prefix):
                return code.removeprefix(prefix).strip("/")
        return code

    @staticmethod
    def _template_code(template_code_or_url: str) -> str:
        code = template_code_or_url.strip()
        for prefix in (
            "https://discord.new/",
            "http://discord.new/",
            "https://discord.com/template/",
            "http://discord.com/template/",
        ):
            if code.startswith(prefix):
                return code.removeprefix(prefix).strip("/")
        return code

    @staticmethod
    def estimate_typing_seconds(
        content: str,
        *,
        wpm: int,
        min_seconds: float,
        max_seconds: float,
    ) -> float:
        if wpm <= 0:
            raise ValueError("wpm must be greater than 0")
        if min_seconds < 0 or max_seconds < 0:
            raise ValueError("typing duration bounds must be non-negative")
        if min_seconds > max_seconds:
            raise ValueError("min_seconds cannot be greater than max_seconds")
        word_count = max(1, len(content.split()))
        estimated_seconds = (word_count / wpm) * 60
        return round(min(max(estimated_seconds, min_seconds), max_seconds), 2)

    async def _simulate_typing(self, channel_id: str, typing_seconds: float) -> None:
        if typing_seconds <= 0:
            return

        deadline = asyncio.get_running_loop().time() + typing_seconds
        while True:
            await self.rest.send_typing_indicator(channel_id)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 8))

    @staticmethod
    def _dm_channel_to_dict(channel: DMChannel) -> dict[str, Any]:
        return {
            "channel_id": channel.id,
            "type": channel.type,
            "name": channel.name,
            "recipient_user_ids": [user.id for user in channel.recipients],
            "recipients": [user.model_dump() for user in channel.recipients],
            "last_message_id": channel.last_message_id,
        }

    @staticmethod
    def _guild_to_dict(guild: DiscordGuild) -> dict[str, Any]:
        return {
            "guild_id": guild.id,
            "name": guild.name,
            "icon": guild.icon,
            "owner": guild.owner,
            "permissions": guild.permissions,
        }

    @staticmethod
    def _server_channel_to_dict(channel: DiscordChannel) -> dict[str, Any]:
        return {
            "channel_id": channel.id,
            "guild_id": channel.guild_id,
            "type": channel.type,
            "name": channel.name,
            "parent_id": channel.parent_id,
            "position": channel.position,
            "topic": channel.topic,
            "last_message_id": channel.last_message_id,
        }

    @staticmethod
    def _message_to_dict(message: DiscordMessage) -> dict[str, Any]:
        return {
            "message_id": message.id,
            "channel_id": message.channel_id,
            "author_id": message.author_id,
            "author_name": message.author_name,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "attachments": message.raw.get("attachments", []),
            "edited_timestamp": message.raw.get("edited_timestamp"),
            "referenced_message_id": (message.raw.get("referenced_message") or {}).get("id"),
        }

    @staticmethod
    def _compact_message_dict(message: dict[str, Any]) -> dict[str, Any]:
        return {
            "message_id": message["message_id"],
            "person": message["author_name"] or message["author_id"],
            "user_id": message["author_id"],
            "message": message["content"],
            "time": message["timestamp"],
        }
