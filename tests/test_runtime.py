from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from discord_user_mcp.config import Settings
from discord_user_mcp.discord.gateway import DiscordGatewayWatcher
from discord_user_mcp.discord.models import DiscordMessage, DiscordUser, DMChannel
from discord_user_mcp.services.runtime import DiscordUserMcpRuntime
from discord_user_mcp.storage.db import DiscordStore


class FakeRest:
    def __init__(self) -> None:
        self.channels = [
            DMChannel(
                id="dm1",
                type=1,
                name="purplecerd",
                recipients=[DiscordUser(id="u1", username="purplecerd")],
                last_message_id="m2",
            )
        ]
        self.sent: list[tuple[str, str]] = []

    async def aclose(self) -> None:
        return None

    async def get_current_user(self) -> dict[str, Any]:
        return {"id": "me"}

    async def list_dm_channels(self) -> list[DMChannel]:
        return self.channels

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
                author_name="purplecerd",
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
        dms = await runtime.list_dms(query="purple")
        assert dms[0]["channel_id"] == "dm1"

        messages = await runtime.read_dm("dm1", limit=5)
        assert messages[0]["content"] == "new message"
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
