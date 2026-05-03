from datetime import UTC, datetime

from discord_user_mcp.discord.models import DiscordMessage, DiscordUser, DMChannel
from discord_user_mcp.storage.db import DiscordStore


def test_store_channels_messages_and_events(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        channel = DMChannel(
            id="dm1",
            type=1,
            name="examplefriend",
            recipients=[DiscordUser(id="u1", username="examplefriend")],
            last_message_id="m1",
        )
        message = DiscordMessage(
            id="m1",
            channel_id="dm1",
            author_id="u1",
            author_name="examplefriend",
            content="hello",
            timestamp=datetime(2026, 5, 1, tzinfo=UTC),
            raw={"id": "m1"},
        )

        store.upsert_dm_channels([channel])
        store.save_message(message, current_user_id="me")
        event_id = store.add_event(
            "dm_message_create",
            channel_id="dm1",
            message_id="m1",
            payload={"content": "hello"},
        )

        events = store.list_events(after_event_id=0)
        assert event_id == 1
        assert store.latest_event_id() == 1
        assert store.latest_event_id(channel_id="dm1") == 1
        assert events == [
            {
                "event_id": 1,
                "event_type": "dm_message_create",
                "channel_id": "dm1",
                "message_id": "m1",
                "payload": {"content": "hello"},
                "created_at": events[0]["created_at"],
            }
        ]
    finally:
        store.close()


def test_active_watch_idle_timeout(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        store.set_active_watch("dm1", context_limit=10, idle_timeout_seconds=0)

        active = store.get_active_watch()
        assert active is not None
        assert active["channel_id"] == "dm1"
        assert active["context_limit"] == 10
        assert active["idle_timeout_seconds"] == 0
        assert store.active_watch_is_idle_expired() is True
    finally:
        store.close()


def test_active_watch_starts_after_existing_events(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        store.add_event(
            "dm_message_create",
            channel_id="dm1",
            message_id="old",
            payload={"content": "old"},
        )
        store.set_active_watch("dm1")

        active = store.get_active_watch()
        assert active is not None
        assert active["last_event_id"] == 1
    finally:
        store.close()
