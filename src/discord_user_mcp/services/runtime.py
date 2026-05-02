from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from discord_user_mcp.config import Settings
from discord_user_mcp.discord.gateway import DiscordGatewayWatcher
from discord_user_mcp.discord.models import DiscordMessage, DMChannel
from discord_user_mcp.discord.rest import DiscordRestClient
from discord_user_mcp.storage.db import DiscordStore


class RestClientProtocol(Protocol):
    async def aclose(self) -> None: ...

    async def get_current_user(self) -> dict[str, Any]: ...

    async def list_dm_channels(self) -> list[DMChannel]: ...

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


@dataclass
class DiscordUserMcpRuntime:
    settings: Settings
    token: str
    store: DiscordStore
    rest: RestClientProtocol
    watcher: DiscordGatewayWatcher
    gateway_task: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> DiscordUserMcpRuntime:
        token = settings.read_token()
        store = DiscordStore(settings.db_path)
        rest = DiscordRestClient(token, base_url=settings.discord_api_base)
        watcher = DiscordGatewayWatcher(token, store, gateway_url=settings.discord_gateway_url)
        return cls(settings=settings, token=token, store=store, rest=rest, watcher=watcher)

    async def start(self) -> None:
        if self.gateway_task is None or self.gateway_task.done():
            self.gateway_task = asyncio.create_task(self.watcher.run_forever())

    async def close(self) -> None:
        self.watcher.stop()
        if self.gateway_task is not None:
            self.gateway_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.gateway_task
        await self.rest.aclose()
        self.store.close()

    async def status(self) -> dict[str, Any]:
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
        channels = await self.rest.list_dm_channels()
        self.store.upsert_dm_channels(channels)
        return [self._channel_to_dict(channel) for channel in channels]

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

    async def read_dm(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[dict[str, Any]]:
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

    async def send_dm(self, channel_id: str, content: str) -> dict[str, Any]:
        if not self.settings.allow_send:
            raise RuntimeError("Sending is disabled by ALLOW_SEND=false")
        message = await self.rest.send_message(channel_id, content)
        self.store.save_message(message, current_user_id=self.watcher.status.current_user_id)
        return self._message_to_dict(message)

    def poll_new_dm_events(
        self,
        *,
        after_event_id: int = 0,
        limit: int = 20,
        channel_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.store.list_events(
            after_event_id=after_event_id,
            channel_id=channel_id,
            limit=limit,
        )

    def start_dm_watch(self, channel_id: str, *, context_limit: int = 30) -> dict[str, Any]:
        self.store.set_active_watch(channel_id, context_limit=context_limit)
        return {"active": True, "channel_id": channel_id, "context_limit": context_limit}

    def stop_dm_watch(self) -> dict[str, Any]:
        self.store.clear_active_watch()
        return {"active": False}

    async def poll_active_dm(
        self,
        *,
        wait_seconds: float = 0,
        max_events: int = 10,
    ) -> dict[str, Any]:
        active = self.store.get_active_watch()
        if active is None:
            return {"active": False, "events": []}

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

    @staticmethod
    def _channel_to_dict(channel: DMChannel) -> dict[str, Any]:
        return {
            "channel_id": channel.id,
            "type": channel.type,
            "name": channel.name,
            "recipient_user_ids": [user.id for user in channel.recipients],
            "recipients": [user.model_dump() for user in channel.recipients],
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
        }
