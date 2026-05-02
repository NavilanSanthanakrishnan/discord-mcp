from __future__ import annotations

from typing import Any

import pytest

from discord_user_mcp.status_rotator import (
    isoformat_utc_after,
    resolve_status_words,
    rotate_custom_status,
    split_status_words,
)


class FakeStatusRestClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def set_custom_status(
        self,
        *,
        text: str | None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "text": text,
            "emoji_name": emoji_name,
            "emoji_id": emoji_id,
            "expires_at": expires_at,
        }
        self.calls.append(payload)
        return {"custom_status": payload}


def test_split_status_words_ignores_extra_whitespace() -> None:
    assert split_status_words("  jump   back   kick back  ") == ["jump", "back", "kick", "back"]


def test_resolve_status_words_prefers_explicit_words() -> None:
    assert resolve_status_words(["Jump", "Back"], "ignored fallback") == ["Jump", "Back"]


def test_isoformat_utc_after_returns_discord_friendly_timestamp() -> None:
    value = isoformat_utc_after(10)
    assert value.endswith("Z")
    assert "T" in value


@pytest.mark.asyncio
async def test_rotate_custom_status_cycles_words_and_clears() -> None:
    rest = FakeStatusRestClient()

    updates = await rotate_custom_status(
        rest=rest,
        words=["jump", "back"],
        interval=0.01,
        emoji_name="🔥",
        max_updates=3,
        clear_on_exit=True,
    )

    assert updates == 3
    assert rest.calls == [
        {"text": "jump", "emoji_name": "🔥", "emoji_id": None, "expires_at": None},
        {"text": "back", "emoji_name": "🔥", "emoji_id": None, "expires_at": None},
        {"text": "jump", "emoji_name": "🔥", "emoji_id": None, "expires_at": None},
        {"text": None, "emoji_name": None, "emoji_id": None, "expires_at": None},
    ]


@pytest.mark.asyncio
async def test_rotate_custom_status_requires_custom_emoji_name_when_id_is_set() -> None:
    rest = FakeStatusRestClient()

    with pytest.raises(ValueError, match="emoji_name is required"):
        await rotate_custom_status(
            rest=rest,
            words=["jump"],
            interval=0.01,
            emoji_id="123",
            max_updates=1,
        )
