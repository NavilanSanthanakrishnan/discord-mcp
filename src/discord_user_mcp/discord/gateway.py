from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets import ClientConnection

from discord_user_mcp.discord.models import DM_CHANNEL_TYPES, DiscordMessage, DMChannel
from discord_user_mcp.storage.db import DiscordStore

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11


@dataclass
class GatewayStatus:
    connected: bool = False
    current_user_id: str | None = None
    known_dm_count: int = 0
    last_sequence: int | None = None
    last_event_type: str | None = None
    last_heartbeat_ack_at: datetime | None = None
    last_error: str | None = None


@dataclass
class DiscordGatewayWatcher:
    token: str
    store: DiscordStore
    gateway_url: str = "wss://gateway.discord.gg/?v=9&encoding=json"
    status: GatewayStatus = field(default_factory=GatewayStatus)

    def __post_init__(self) -> None:
        self._dm_channel_ids: set[str] = set()
        self._stop_event = asyncio.Event()

    @property
    def dm_channel_ids(self) -> frozenset[str]:
        return frozenset(self._dm_channel_ids)

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:  # pragma: no cover - exercised in live runtime
                self.status.connected = False
                self.status.last_error = str(exc)
                await asyncio.sleep(5)

    async def run_once(self) -> None:
        async with websockets.connect(self.gateway_url, max_size=None) as websocket:
            self.status.connected = True
            await self._session(websocket)

    async def _session(self, websocket: ClientConnection) -> None:
        raw_hello = await websocket.recv()
        hello = json.loads(raw_hello)
        if hello.get("op") != OP_HELLO:
            raise RuntimeError("Discord Gateway did not send HELLO")

        heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket, heartbeat_interval))
        try:
            await websocket.send(json.dumps(self._identify_payload()))

            async for raw in websocket:
                payload = json.loads(raw)
                await self.handle_payload(payload)
                if payload.get("op") in {OP_RECONNECT, OP_INVALID_SESSION}:
                    break
                if self._stop_event.is_set():
                    break
        finally:
            heartbeat_task.cancel()
            self.status.connected = False

    async def _heartbeat_loop(self, websocket: ClientConnection, heartbeat_interval: float) -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            await websocket.send(json.dumps({"op": OP_HEARTBEAT, "d": self.status.last_sequence}))

    def _identify_payload(self) -> dict[str, Any]:
        return {
            "op": OP_IDENTIFY,
            "d": {
                "token": self.token,
                "capabilities": 8189,
                "properties": {
                    "os": "macOS",
                    "browser": "Chrome",
                    "device": "",
                },
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False,
                },
                "compress": False,
                "client_state": {"guild_versions": {}},
            },
        }

    async def handle_payload(self, payload: dict[str, Any]) -> None:
        sequence = payload.get("s")
        if sequence is not None:
            self.status.last_sequence = sequence

        op = payload.get("op")
        if op == OP_HEARTBEAT_ACK:
            self.status.last_heartbeat_ack_at = datetime.now(UTC)
            return

        if op != OP_DISPATCH:
            return

        event_type = payload.get("t")
        data = payload.get("d") or {}
        self.status.last_event_type = event_type

        if event_type == "READY":
            self._handle_ready(data)
        elif event_type == "CHANNEL_CREATE":
            self._handle_channel_create(data)
        elif event_type == "MESSAGE_CREATE":
            self._handle_message_create(data)
        elif event_type == "TYPING_START":
            self._handle_typing_start(data)

    def _handle_ready(self, data: dict[str, Any]) -> None:
        self.status.current_user_id = data.get("user", {}).get("id")
        channels = [
            DMChannel.from_discord(channel)
            for channel in data.get("private_channels", [])
            if channel.get("type") in DM_CHANNEL_TYPES
        ]
        self._dm_channel_ids = {channel.id for channel in channels}
        self.status.known_dm_count = len(self._dm_channel_ids)
        self.store.upsert_dm_channels(channels)

    def _handle_channel_create(self, data: dict[str, Any]) -> None:
        if data.get("type") not in DM_CHANNEL_TYPES:
            return
        channel = DMChannel.from_discord(data)
        self._dm_channel_ids.add(channel.id)
        self.status.known_dm_count = len(self._dm_channel_ids)
        self.store.upsert_dm_channels([channel])

    def _handle_message_create(self, data: dict[str, Any]) -> None:
        channel_id = data.get("channel_id")
        if not channel_id:
            return

        is_dm = channel_id in self._dm_channel_ids or not data.get("guild_id")
        if not is_dm:
            return

        message = DiscordMessage.from_discord(data)
        self.store.save_message(message, current_user_id=self.status.current_user_id)

        author_id = data.get("author", {}).get("id")
        if author_id == self.status.current_user_id:
            return

        self.store.add_event(
            "dm_message_create",
            channel_id=message.channel_id,
            message_id=message.id,
            payload={
                "message": message.model_dump(mode="json"),
                "raw": data,
            },
        )

    def _handle_typing_start(self, data: dict[str, Any]) -> None:
        channel_id = data.get("channel_id")
        user_id = data.get("user_id")
        if not channel_id or not user_id:
            return
        if user_id == self.status.current_user_id:
            return

        is_dm = channel_id in self._dm_channel_ids or not data.get("guild_id")
        if not is_dm:
            return

        self.store.add_event(
            "dm_typing_start",
            channel_id=channel_id,
            message_id=None,
            payload={
                "user_id": user_id,
                "timestamp": data.get("timestamp"),
                "raw": data,
            },
        )
