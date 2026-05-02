from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from discord_user_mcp.discord.models import DiscordMessage, DMChannel

SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_channels (
    channel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    recipients_json TEXT NOT NULL,
    last_message_id TEXT,
    is_active_watch INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_from_self INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_channel_event_id ON events(channel_id, event_id);
CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp ON messages(channel_id, timestamp);

CREATE TABLE IF NOT EXISTS active_watch (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    channel_id TEXT NOT NULL,
    context_limit INTEGER NOT NULL DEFAULT 30,
    last_event_id INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class DiscordStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def upsert_dm_channels(self, channels: Iterable[DMChannel]) -> None:
        with self._conn:
            for channel in channels:
                recipients_json = json.dumps([user.model_dump() for user in channel.recipients])
                self._conn.execute(
                    """
                    INSERT INTO dm_channels(channel_id, name, recipients_json, last_message_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        name = excluded.name,
                        recipients_json = excluded.recipients_json,
                        last_message_id = excluded.last_message_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (channel.id, channel.name, recipients_json, channel.last_message_id),
                )

    def list_dm_channels(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT channel_id, name, recipients_json, last_message_id
            FROM dm_channels
            ORDER BY COALESCE(last_message_id, '0') DESC
            """
        ).fetchall()
        return [
            {
                "channel_id": row["channel_id"],
                "name": row["name"],
                "recipients": json.loads(row["recipients_json"]),
                "recipient_user_ids": [
                    recipient["id"] for recipient in json.loads(row["recipients_json"])
                ],
                "last_message_id": row["last_message_id"],
            }
            for row in rows
        ]

    def save_message(self, message: DiscordMessage, *, current_user_id: str | None = None) -> None:
        is_from_self = int(current_user_id is not None and message.author_id == current_user_id)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO messages(
                    message_id, channel_id, author_id, author_name, content, timestamp,
                    is_from_self, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    content = excluded.content,
                    raw_json = excluded.raw_json
                """,
                (
                    message.id,
                    message.channel_id,
                    message.author_id,
                    message.author_name,
                    message.content,
                    message.timestamp.isoformat(),
                    is_from_self,
                    json.dumps(message.raw),
                ),
            )

    def add_event(
        self,
        event_type: str,
        *,
        channel_id: str,
        message_id: str | None,
        payload: dict[str, Any],
    ) -> int:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO events(event_type, channel_id, message_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, channel_id, message_id, json.dumps(payload)),
            )
            return int(cursor.lastrowid)

    def list_events(
        self,
        *,
        after_event_id: int = 0,
        channel_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if channel_id:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE event_id > ? AND channel_id = ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (after_event_id, channel_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (after_event_id, limit),
            ).fetchall()

        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "channel_id": row["channel_id"],
                "message_id": row["message_id"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def set_active_watch(self, channel_id: str, *, context_limit: int = 30) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO active_watch(singleton_id, channel_id, context_limit, last_event_id)
                VALUES (1, ?, ?, 0)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    context_limit = excluded.context_limit,
                    last_event_id = 0,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (channel_id, context_limit),
            )

    def get_active_watch(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT channel_id, context_limit, last_event_id
            FROM active_watch
            WHERE singleton_id = 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "channel_id": row["channel_id"],
            "context_limit": row["context_limit"],
            "last_event_id": row["last_event_id"],
        }

    def update_active_watch_last_event(self, event_id: int) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE active_watch
                SET last_event_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE singleton_id = 1
                """,
                (event_id,),
            )

    def clear_active_watch(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM active_watch WHERE singleton_id = 1")
