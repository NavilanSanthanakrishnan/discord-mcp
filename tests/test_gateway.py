from datetime import UTC, datetime

import pytest

from discord_user_mcp.discord.gateway import DiscordGatewayWatcher
from discord_user_mcp.storage.db import DiscordStore


@pytest.mark.asyncio
async def test_ready_caches_private_channels(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        watcher = DiscordGatewayWatcher("token", store)
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 1,
                "t": "READY",
                "d": {
                    "user": {"id": "me"},
                    "private_channels": [
                        {
                            "id": "dm1",
                            "type": 1,
                            "recipients": [{"id": "u1", "username": "examplefriend"}],
                            "last_message_id": "m1",
                        },
                        {"id": "guild-channel", "type": 0, "name": "general"},
                    ],
                },
            }
        )

        assert watcher.status.current_user_id == "me"
        assert watcher.status.known_dm_count == 1
        assert watcher.dm_channel_ids == frozenset({"dm1"})
    finally:
        store.close()


@pytest.mark.asyncio
async def test_message_create_from_dm_adds_event(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        watcher = DiscordGatewayWatcher("token", store)
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 1,
                "t": "READY",
                "d": {
                    "user": {"id": "me"},
                    "private_channels": [
                        {
                            "id": "dm1",
                            "type": 1,
                            "recipients": [{"id": "u1", "username": "examplefriend"}],
                        }
                    ],
                },
            }
        )
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 2,
                "t": "MESSAGE_CREATE",
                "d": {
                    "id": "m1",
                    "channel_id": "dm1",
                    "content": "hello from examplefriend",
                    "timestamp": "2026-05-01T00:00:00+00:00",
                    "author": {"id": "u1", "username": "examplefriend"},
                },
            }
        )

        events = store.list_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "dm_message_create"
        assert events[0]["payload"]["message"]["content"] == "hello from examplefriend"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_message_create_from_self_is_stored_but_not_evented(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        watcher = DiscordGatewayWatcher("token", store)
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 1,
                "t": "READY",
                "d": {
                    "user": {"id": "me"},
                    "private_channels": [{"id": "dm1", "type": 1, "recipients": []}],
                },
            }
        )
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 2,
                "t": "MESSAGE_CREATE",
                "d": {
                    "id": "m2",
                    "channel_id": "dm1",
                    "content": "my reply",
                    "timestamp": datetime(2026, 5, 1, tzinfo=UTC).isoformat(),
                    "author": {"id": "me", "username": "me"},
                },
            }
        )

        assert store.list_events() == []
    finally:
        store.close()


@pytest.mark.asyncio
async def test_typing_start_from_dm_adds_event(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        watcher = DiscordGatewayWatcher("token", store)
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 1,
                "t": "READY",
                "d": {
                    "user": {"id": "me"},
                    "private_channels": [{"id": "dm1", "type": 1, "recipients": []}],
                },
            }
        )
        await watcher.handle_payload(
            {
                "op": 0,
                "s": 2,
                "t": "TYPING_START",
                "d": {
                    "channel_id": "dm1",
                    "user_id": "u1",
                    "timestamp": 1770000000,
                },
            }
        )

        events = store.list_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "dm_typing_start"
        assert events[0]["payload"]["user_id"] == "u1"
    finally:
        store.close()
