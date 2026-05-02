from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from discord_user_mcp.config import Settings
from discord_user_mcp.discord.rest import DiscordRestClient

DEFAULT_ROTATOR_TEXT = "jump back kick back"


class StatusWriter(Protocol):
    async def set_custom_status(
        self,
        *,
        text: str | None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, object]: ...


def split_status_words(text: str) -> list[str]:
    return [word for word in text.split() if word]


def resolve_status_words(words: Sequence[str], text: str) -> list[str]:
    resolved = [word.strip() for word in words if word.strip()]
    if resolved:
        return resolved

    resolved = split_status_words(text)
    if resolved:
        return resolved

    raise ValueError("at least one status word is required")


def isoformat_utc_after(seconds: float) -> str:
    expires_at = datetime.now(UTC) + timedelta(seconds=seconds)
    return expires_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def rotate_custom_status(
    *,
    rest: StatusWriter,
    words: Sequence[str],
    interval: float,
    emoji_name: str | None = None,
    emoji_id: str | None = None,
    expires_in_seconds: float | None = None,
    max_updates: int | None = None,
    clear_on_exit: bool = False,
) -> int:
    if not words:
        raise ValueError("at least one status word is required")
    if interval <= 0:
        raise ValueError("interval must be greater than 0")
    if max_updates is not None and max_updates <= 0:
        raise ValueError("max_updates must be greater than 0 when provided")
    if emoji_id is not None and not emoji_name:
        raise ValueError("emoji_name is required when emoji_id is provided")

    update_count = 0
    index = 0

    try:
        while max_updates is None or update_count < max_updates:
            word = words[index % len(words)]
            expires_at = (
                isoformat_utc_after(expires_in_seconds)
                if expires_in_seconds is not None
                else None
            )
            await rest.set_custom_status(
                text=word,
                emoji_name=emoji_name,
                emoji_id=emoji_id,
                expires_at=expires_at,
            )
            update_count += 1
            index += 1
            print(
                f"[{update_count}] custom status -> {word}"
                + (f" {emoji_name}" if emoji_name else "")
            )
            if max_updates is not None and update_count >= max_updates:
                break
            await asyncio.sleep(interval)
    finally:
        if clear_on_exit:
            await rest.set_custom_status(
                text=None,
                emoji_name=None,
                emoji_id=None,
                expires_at=None,
            )
            print("custom status cleared")

    return update_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rotate your Discord custom status one word at a time using the JSON "
            "users/@me/settings endpoint."
        )
    )
    parser.add_argument(
        "words",
        nargs="*",
        help=(
            "Explicit status words to cycle. If omitted, --text is split on spaces. "
            "Default: 'jump back kick back'."
        ),
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_ROTATOR_TEXT,
        help="Fallback phrase to split into words when no positional words are supplied.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds to wait before moving to the next word.",
    )
    parser.add_argument(
        "--emoji-name",
        help="Optional unicode emoji or custom emoji name to attach to every word.",
    )
    parser.add_argument(
        "--emoji-id",
        help="Optional custom Discord emoji ID. Use together with --emoji-name.",
    )
    parser.add_argument(
        "--expires-in-seconds",
        type=float,
        help="Optional per-update expiration horizon. The script refreshes it on every change.",
    )
    parser.add_argument(
        "--max-updates",
        type=int,
        help="Optional cap for smoke tests. Omit to run forever.",
    )
    parser.add_argument(
        "--clear-on-exit",
        action="store_true",
        help="Clear the custom status when the process exits or is interrupted.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Settings.from_env().token_file,
        help="Path to the Discord user token file. Defaults to DISCORD_TOKEN_FILE or repo default.",
    )
    parser.add_argument(
        "--api-base",
        default=Settings.from_env().discord_api_base,
        help="Discord API base URL. Defaults to DISCORD_API_BASE or https://discord.com/api/v9.",
    )
    return parser.parse_args()


async def _run_from_args(args: argparse.Namespace) -> int:
    words = resolve_status_words(args.words, args.text)
    settings = Settings.from_env()
    token = Settings(
        token_file=args.token_file,
        db_path=settings.db_path,
        discord_api_base=args.api_base,
        discord_gateway_url=settings.discord_gateway_url,
        mcp_host=settings.mcp_host,
        mcp_port=settings.mcp_port,
        allow_send=settings.allow_send,
        natural_typing_wpm=settings.natural_typing_wpm,
        natural_typing_min_seconds=settings.natural_typing_min_seconds,
        natural_typing_max_seconds=settings.natural_typing_max_seconds,
    ).read_token()

    rest = DiscordRestClient(token, base_url=args.api_base)
    try:
        return await rotate_custom_status(
            rest=rest,
            words=words,
            interval=args.interval,
            emoji_name=args.emoji_name,
            emoji_id=args.emoji_id,
            expires_in_seconds=args.expires_in_seconds,
            max_updates=args.max_updates,
            clear_on_exit=args.clear_on_exit,
        )
    finally:
        await rest.aclose()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(_run_from_args(args))
    except KeyboardInterrupt:
        print("status rotator stopped")


if __name__ == "__main__":
    main()
