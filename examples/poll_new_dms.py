"""Tiny non-AI poller for new Discord DM events.

Run this from cron/launchd/a supervisor to wake your real agent only when
`poll_new_dm_events` returns work. This script itself spends zero model tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_MCP_URL = "http://127.0.0.1:8085/mcp"
DEFAULT_CURSOR_FILE = Path(".local/poll_new_dms_cursor.json")


def load_cursor(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["last_event_id"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return 0


def save_cursor(path: Path, event_id: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_event_id": event_id}, indent=2), encoding="utf-8")


def decode_tool_result(result: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in result.content:
        text = getattr(item, "text", "")
        if text:
            payload = json.loads(text)
            if isinstance(payload, list):
                events.extend(payload)
            else:
                events.append(payload)
    return events


async def poll_once(mcp_url: str, cursor_file: Path, limit: int) -> int:
    after_event_id = load_cursor(cursor_file)
    async with (
        streamablehttp_client(mcp_url) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "poll_new_dm_events",
            {"after_event_id": after_event_id, "limit": limit},
        )

    events = decode_tool_result(result)
    if not events:
        print("no new DM events")
        return after_event_id

    latest_event_id = max(int(event["event_id"]) for event in events)
    save_cursor(cursor_file, latest_event_id)
    for event in events:
        payload = event.get("payload", {})
        message = payload.get("message", payload)
        print(
            json.dumps(
                {
                    "event_id": event.get("event_id"),
                    "channel_id": event.get("channel_id"),
                    "message_id": event.get("message_id"),
                    "author_name": message.get("author_name"),
                    "preview": (message.get("content") or "")[:120],
                },
                ensure_ascii=False,
            )
        )
    return latest_event_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Discord MCP for new DM events once.")
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--cursor-file", type=Path, default=DEFAULT_CURSOR_FILE)
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(poll_once(args.mcp_url, args.cursor_file, args.limit))


if __name__ == "__main__":
    main()
