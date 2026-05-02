from datetime import UTC, datetime

from discord_user_mcp.discord.models import DiscordMessage, DiscordUser, DMChannel
from discord_user_mcp.storage.db import DiscordStore


def test_store_channels_messages_and_events(tmp_path) -> None:
    store = DiscordStore(tmp_path / "state.sqlite")
    try:
        channel = DMChannel(
            id="dm1",
            type=1,
            name="purplecerd",
            recipients=[DiscordUser(id="u1", username="purplecerd")],
            last_message_id="m1",
        )
        message = DiscordMessage(
            id="m1",
            channel_id="dm1",
            author_id="u1",
            author_name="purplecerd",
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
