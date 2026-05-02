from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

DISCORD_EPOCH_MS = 1420070400000
DM_CHANNEL_TYPES = {1, 3}


def snowflake_to_datetime(snowflake: str) -> datetime:
    timestamp_ms = (int(snowflake) >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


class DiscordUser(BaseModel):
    id: str
    username: str | None = None
    global_name: str | None = None

    @property
    def display_name(self) -> str:
        return self.global_name or self.username or self.id


class DMChannel(BaseModel):
    id: str
    type: int
    name: str
    recipients: list[DiscordUser] = Field(default_factory=list)
    last_message_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_discord(cls, payload: dict[str, Any]) -> DMChannel:
        recipients = [DiscordUser.model_validate(user) for user in payload.get("recipients", [])]
        name = (
            payload.get("name")
            or ", ".join(user.display_name for user in recipients)
            or payload["id"]
        )
        return cls(
            id=payload["id"],
            type=payload["type"],
            name=name,
            recipients=recipients,
            last_message_id=payload.get("last_message_id"),
            raw=payload,
        )


class DiscordMessage(BaseModel):
    id: str
    channel_id: str
    author_id: str
    author_name: str
    content: str
    timestamp: datetime
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_discord(cls, payload: dict[str, Any]) -> DiscordMessage:
        author = payload.get("author", {})
        timestamp_raw = payload.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            if timestamp_raw
            else snowflake_to_datetime(payload["id"])
        )
        return cls(
            id=payload["id"],
            channel_id=payload["channel_id"],
            author_id=author.get("id", ""),
            author_name=author.get("global_name") or author.get("username") or author.get("id", ""),
            content=payload.get("content", ""),
            timestamp=timestamp,
            raw=payload,
        )
