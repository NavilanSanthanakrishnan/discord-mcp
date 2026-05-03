from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from discord_user_mcp.config import Settings
from discord_user_mcp.discord.gateway import DiscordGatewayWatcher
from discord_user_mcp.discord.models import (
    DiscordChannel,
    DiscordGuild,
    DiscordMessage,
    DiscordUser,
    DMChannel,
)
from discord_user_mcp.services.runtime import DiscordUserMcpRuntime
from discord_user_mcp.storage.db import DiscordStore


class FakeRest:
    def __init__(self) -> None:
        self.channels = [
            DMChannel(
                id="dm1",
                type=1,
                name="examplefriend",
                recipients=[DiscordUser(id="u1", username="examplefriend")],
                last_message_id="m2",
            )
        ]
        self.guilds = [
            DiscordGuild(id="guild1", name="Test Server", owner=False, permissions="123")
        ]
        self.guild_channels = [
            DiscordChannel(
                id="chan1",
                type=0,
                name="general",
                guild_id="guild1",
                position=1,
            )
        ]
        self.sent: list[tuple[str, str]] = []
        self.replies: list[tuple[str, str, str]] = []
        self.edited: list[tuple[str, str, str]] = []
        self.deleted: list[tuple[str, str]] = []
        self.added_reactions: list[tuple[str, str, str]] = []
        self.removed_reactions: list[tuple[str, str, str]] = []
        self.typing_channel_ids: list[str] = []
        self.attachment_sends: list[tuple[str, list[str], str | None]] = []
        self.custom_status: dict[str, Any] | None = {
            "text": "working",
            "emoji_name": None,
            "emoji_id": None,
            "expires_at": None,
        }
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True
        return None

    async def get_current_user(self) -> dict[str, Any]:
        return {"id": "me"}

    async def get_user_settings(self) -> dict[str, Any]:
        return {"status": "dnd", "custom_status": self.custom_status}

    async def set_custom_status(
        self,
        *,
        text: str | None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        self.custom_status = (
            None
            if text is None and emoji_name is None and emoji_id is None and expires_at is None
            else {
                "text": text,
                "emoji_name": emoji_name,
                "emoji_id": emoji_id,
                "expires_at": expires_at,
            }
        )
        return {"status": "dnd", "custom_status": self.custom_status}

    async def list_dm_channels(self) -> list[DMChannel]:
        return self.channels

    async def list_guilds(self) -> list[DiscordGuild]:
        return self.guilds

    async def list_guild_channels(self, guild_id: str) -> list[DiscordChannel]:
        return [channel for channel in self.guild_channels if channel.guild_id == guild_id]

    async def read_messages(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[DiscordMessage]:
        return [
            DiscordMessage(
                id="m2",
                channel_id=channel_id,
                author_id="u1",
                author_name="examplefriend",
                content="new message",
                timestamp=datetime(2026, 5, 1, tzinfo=UTC),
                raw={"id": "m2"},
            )
        ][:limit]

    async def send_message(self, channel_id: str, content: str) -> DiscordMessage:
        self.sent.append((channel_id, content))
        return DiscordMessage(
            id="m3",
            channel_id=channel_id,
            author_id="me",
            author_name="me",
            content=content,
            timestamp=datetime(2026, 5, 1, 0, 0, 1, tzinfo=UTC),
            raw={"id": "m3"},
        )

    async def reply_to_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage:
        self.replies.append((channel_id, message_id, content))
        return DiscordMessage(
            id="m-reply",
            channel_id=channel_id,
            author_id="me",
            author_name="me",
            content=content,
            timestamp=datetime(2026, 5, 1, 0, 0, 1, tzinfo=UTC),
            raw={
                "id": "m-reply",
                "referenced_message": {"id": message_id},
            },
        )

    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage:
        self.edited.append((channel_id, message_id, content))
        return DiscordMessage(
            id=message_id,
            channel_id=channel_id,
            author_id="me",
            author_name="me",
            content=content,
            timestamp=datetime(2026, 5, 1, 0, 0, 2, tzinfo=UTC),
            raw={"id": message_id, "edited_timestamp": "2026-05-01T00:00:02+00:00"},
        )

    async def delete_message(self, channel_id: str, message_id: str) -> None:
        self.deleted.append((channel_id, message_id))

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.added_reactions.append((channel_id, message_id, emoji))

    async def remove_own_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.removed_reactions.append((channel_id, message_id, emoji))

    async def send_typing_indicator(self, channel_id: str) -> None:
        self.typing_channel_ids.append(channel_id)

    async def send_message_with_attachments(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        attachment_paths: list[str],
    ) -> DiscordMessage:
        self.attachment_sends.append((channel_id, attachment_paths, content))
        return DiscordMessage(
            id="m4",
            channel_id=channel_id,
            author_id="me",
            author_name="me",
            content=content or "",
            timestamp=datetime(2026, 5, 1, 0, 0, 3, tzinfo=UTC),
            raw={
                "id": "m4",
                "attachments": [{"id": "a1", "filename": "image.png"}],
            },
        )


def make_runtime(tmp_path: Path, *, allow_send: bool = True) -> DiscordUserMcpRuntime:
    settings = Settings(
        token_file=tmp_path / "token.txt",
        db_path=tmp_path / "state.sqlite",
        allow_send=allow_send,
    )
    store = DiscordStore(settings.db_path)
    watcher = DiscordGatewayWatcher("token", store)
    watcher.status.current_user_id = "me"
    return DiscordUserMcpRuntime(
        settings=settings,
        token="token",
        store=store,
        rest=FakeRest(),
        watcher=watcher,
        gateway_enabled=False,
    )


@pytest.mark.asyncio
async def test_list_and_read_dms(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        dms = await runtime.list_dms(query="example")
        assert dms[0]["channel_id"] == "dm1"

        messages = await runtime.read_dm("dm1", limit=5)
        assert messages[0]["content"] == "new message"

        compact = await runtime.read_messages("dm1", limit=5)
        assert compact == [
            {
                "message_id": "m2",
                "person": "examplefriend",
                "user_id": "u1",
                "message": "new message",
                "time": "2026-05-01T00:00:00+00:00",
            }
        ]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_get_and_set_custom_status(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        current = await runtime.get_custom_status()
        assert current["custom_status"]["text"] == "working"

        updated = await runtime.set_custom_status(text="ship it", emoji_name="🚢")
        assert updated == {
            "status": "dnd",
            "custom_status": {
                "text": "ship it",
                "emoji_name": "🚢",
                "emoji_id": None,
                "expires_at": None,
            },
        }

        cleared = await runtime.set_custom_status()
        assert cleared == {"status": "dnd", "custom_status": None}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_list_servers_and_server_channels(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        servers = await runtime.list_servers(query="test")
        assert servers == [
            {
                "guild_id": "guild1",
                "name": "Test Server",
                "icon": None,
                "owner": False,
                "permissions": "123",
            }
        ]

        channels = await runtime.list_server_channels("guild1", query="general")
        assert channels[0]["channel_id"] == "chan1"
        assert channels[0]["guild_id"] == "guild1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_send_dm_can_be_disabled(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, allow_send=False)
    try:
        with pytest.raises(RuntimeError, match="Sending is disabled"):
            await runtime.send_dm("dm1", "hello")
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_edit_delete_typing_and_attachments(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        reply = await runtime.reply_to_dm_message("dm1", "m2", "replying here")
        assert reply["content"] == "replying here"
        assert reply["referenced_message_id"] == "m2"
        assert runtime.rest.replies == [("dm1", "m2", "replying here")]

        edited = await runtime.edit_dm_message("dm1", "m3", "fixed")
        assert edited["content"] == "fixed"
        assert runtime.rest.edited == [("dm1", "m3", "fixed")]

        deleted = await runtime.delete_dm_message("dm1", "m3")
        assert deleted == {"deleted": True, "channel_id": "dm1", "message_id": "m3"}
        assert runtime.rest.deleted == [("dm1", "m3")]

        reaction = await runtime.add_dm_reaction("dm1", "m2", "🔥")
        assert reaction == {
            "reacted": True,
            "channel_id": "dm1",
            "message_id": "m2",
            "emoji": "🔥",
        }
        assert runtime.rest.added_reactions == [("dm1", "m2", "🔥")]

        removed = await runtime.remove_dm_reaction("dm1", "m2", "🔥")
        assert removed == {
            "removed": True,
            "channel_id": "dm1",
            "message_id": "m2",
            "emoji": "🔥",
        }
        assert runtime.rest.removed_reactions == [("dm1", "m2", "🔥")]

        typing = await runtime.send_typing_indicator("dm1")
        assert typing == {"typing": True, "channel_id": "dm1"}
        assert runtime.rest.typing_channel_ids == ["dm1"]

        sent = await runtime.send_dm_attachments(
            "dm1",
            attachment_paths=["/tmp/image.png"],
            content="see this",
        )
        assert sent["attachments"] == [{"id": "a1", "filename": "image.png"}]
        assert runtime.rest.attachment_sends == [("dm1", ["/tmp/image.png"], "see this")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_send_natural_dm_types_before_sending(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        sent = await runtime.send_natural_dm(
            "dm1",
            "hello there",
            wpm=120,
            min_seconds=0,
            max_seconds=0,
        )

        assert sent["content"] == "hello there"
        assert sent["typing_seconds"] == 0
        assert runtime.rest.sent == [("dm1", "hello there")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_send_natural_message_works_for_any_channel(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        sent = await runtime.send_natural_message(
            "chan1",
            "hello server",
            wpm=120,
            min_seconds=0,
            max_seconds=0,
        )

        assert sent["content"] == "hello server"
        assert sent["typing_seconds"] == 0
        assert runtime.rest.sent == [("chan1", "hello server")]
    finally:
        await runtime.close()


def test_estimate_typing_seconds_clamps_duration(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        assert runtime.estimate_typing_seconds(
            "one two three four",
            wpm=60,
            min_seconds=1,
            max_seconds=2,
        ) == 2
        assert runtime.estimate_typing_seconds(
            "one",
            wpm=60,
            min_seconds=1.5,
            max_seconds=10,
        ) == 1.5
    finally:
        runtime.store.close()


@pytest.mark.asyncio
async def test_active_watch_polls_incrementally(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        runtime.start_dm_watch("dm1")
        runtime.store.add_event(
            "dm_message_create",
            channel_id="dm1",
            message_id="m1",
            payload={"message": {"content": "first"}},
        )

        first = await runtime.poll_active_dm()
        assert [event["message_id"] for event in first["events"]] == ["m1"]

        second = await runtime.poll_active_dm()
        assert second["events"] == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_collect_dm_burst_waits_for_quiet_period(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        runtime.store.add_event(
            "dm_typing_start",
            channel_id="dm1",
            message_id=None,
            payload={"user_id": "u1"},
        )
        runtime.store.add_event(
            "dm_message_create",
            channel_id="dm1",
            message_id="m1",
            payload={"message": {"content": "first"}},
        )
        runtime.store.add_event(
            "dm_message_create",
            channel_id="dm1",
            message_id="m2",
            payload={"message": {"content": "second"}},
        )

        burst = await runtime.collect_dm_burst(
            "dm1",
            quiet_seconds=0,
            max_wait_seconds=0,
            max_events=10,
            typing_ttl_seconds=0,
        )

        assert burst["ended_reason"] in {"quiet_period", "max_wait"}
        assert burst["typing_observed"] is True
        assert [event["message_id"] for event in burst["events"]] == ["m1", "m2"]
        assert burst["last_event_id"] == 3
    finally:
        await runtime.close()
