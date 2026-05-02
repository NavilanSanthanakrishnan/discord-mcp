from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

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

    async def refresh_dms(self) -> list[dict[str, Any]]:
        await self.start()
        channels = await self.rest.list_dm_channels()
        self.store.upsert_dm_channels(channels)
        return [self._dm_channel_to_dict(channel) for channel in channels]

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
