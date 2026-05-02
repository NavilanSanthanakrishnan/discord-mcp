from __future__ import annotations

import json
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from discord_user_mcp.discord.models import (
    DM_CHANNEL_TYPES,
    GUILD_TEXT_CHANNEL_TYPES,
    DiscordChannel,
    DiscordGuild,
    DiscordMessage,
    DMChannel,
)


class DiscordRestError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"Discord REST request failed ({status_code}): {message}")
        self.status_code = status_code
        self.message = message


class DiscordRestClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://discord.com/api/v9",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._token,
            "Content-Type": "application/json",
            "User-Agent": "DiscordMCP/0.1",
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any | None] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        response = await self._client.request(
            method,
            url,
            headers=self._headers(),
            params=clean_params,
            json=json_body,
        )
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("message", response.text)
            except ValueError:
                message = response.text
            raise DiscordRestError(response.status_code, message)
        if not response.content:
            return None
        return response.json()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any | None] | None = None,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        headers = self._headers()
        if files is not None:
            headers.pop("Content-Type", None)
        response = await self._client.request(
            method,
            url,
            headers=headers,
            params=clean_params,
            json=json_body if files is None else None,
            files=files,
        )
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("message", response.text)
            except ValueError:
                message = response.text
            raise DiscordRestError(response.status_code, message)
        return response

    async def get_current_user(self) -> dict[str, Any]:
        return await self._request_json("GET", "users/@me")

    async def get_user_settings(self) -> dict[str, Any]:
        return await self._request_json("GET", "users/@me/settings")

    async def set_custom_status(
        self,
        *,
        text: str | None,
        emoji_name: str | None = None,
        emoji_id: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        custom_status: dict[str, Any] | None
        if text is None and emoji_name is None and emoji_id is None and expires_at is None:
            custom_status = None
        else:
            custom_status = {
                "text": text,
                "emoji_name": emoji_name,
                "emoji_id": emoji_id,
                "expires_at": expires_at,
            }
        return await self._request_json(
            "PATCH",
            "users/@me/settings",
            json_body={"custom_status": custom_status},
        )

    async def list_dm_channels(self) -> list[DMChannel]:
        payload = await self._request_json("GET", "users/@me/channels")
        return [
            DMChannel.from_discord(channel)
            for channel in payload
            if channel.get("type") in DM_CHANNEL_TYPES
        ]

    async def list_guilds(self) -> list[DiscordGuild]:
        payload = await self._request_json("GET", "users/@me/guilds")
        return [DiscordGuild.from_discord(guild) for guild in payload]

    async def list_guild_channels(self, guild_id: str) -> list[DiscordChannel]:
        payload = await self._request_json("GET", f"guilds/{guild_id}/channels")
        return [
            DiscordChannel.from_discord(channel)
            for channel in payload
            if channel.get("type") in GUILD_TEXT_CHANNEL_TYPES
        ]

    async def read_messages(
        self,
        channel_id: str,
        *,
        limit: int = 20,
        before: str | None = None,
        after: str | None = None,
        around: str | None = None,
    ) -> list[DiscordMessage]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        cursor_count = sum(value is not None for value in (before, after, around))
        if cursor_count > 1:
            raise ValueError("only one of before, after, or around can be provided")

        payload = await self._request_json(
            "GET",
            f"channels/{channel_id}/messages",
            params={"limit": limit, "before": before, "after": after, "around": around},
        )
        return [DiscordMessage.from_discord(message) for message in payload]

    async def send_message(self, channel_id: str, content: str) -> DiscordMessage:
        if not content.strip():
            raise ValueError("content must not be blank")
        payload = await self._request_json(
            "POST",
            f"channels/{channel_id}/messages",
            json_body={"content": content},
        )
        return DiscordMessage.from_discord(payload)

    async def reply_to_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage:
        if not content.strip():
            raise ValueError("content must not be blank")
        payload = await self._request_json(
            "POST",
            f"channels/{channel_id}/messages",
            json_body={
                "content": content,
                "message_reference": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "fail_if_not_exists": True,
                },
            },
        )
        return DiscordMessage.from_discord(payload)

    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage:
        if not content.strip():
            raise ValueError("content must not be blank")
        payload = await self._request_json(
            "PATCH",
            f"channels/{channel_id}/messages/{message_id}",
            json_body={"content": content},
        )
        return DiscordMessage.from_discord(payload)

    async def delete_message(self, channel_id: str, message_id: str) -> None:
        await self._request_json("DELETE", f"channels/{channel_id}/messages/{message_id}")

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        encoded_emoji = quote(emoji, safe="")
        await self._request_json(
            "PUT",
            f"channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
        )

    async def remove_own_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        encoded_emoji = quote(emoji, safe="")
        await self._request_json(
            "DELETE",
            f"channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
        )

    async def send_typing_indicator(self, channel_id: str) -> None:
        await self._request_json("POST", f"channels/{channel_id}/typing")

    async def send_message_with_attachments(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        attachment_paths: list[str],
    ) -> DiscordMessage:
        if not attachment_paths:
            raise ValueError("attachment_paths must contain at least one file")
        if content is not None and not content.strip():
            raise ValueError("content must not be blank when provided")

        file_parts: dict[str, Any] = {
            "payload_json": (
                None,
                json.dumps({"content": content or ""}),
                "application/json",
            )
        }
        opened_files = []
        try:
            for index, attachment_path in enumerate(attachment_paths):
                path = Path(attachment_path).expanduser()
                if not path.is_file():
                    raise FileNotFoundError(f"Attachment file not found: {path}")
                file_obj = path.open("rb")
                opened_files.append(file_obj)
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                file_parts[f"files[{index}]"] = (path.name, file_obj, content_type)

            response = await self._request(
                "POST",
                f"channels/{channel_id}/messages",
                files=file_parts,
            )
        finally:
            for file_obj in opened_files:
                file_obj.close()

        return DiscordMessage.from_discord(response.json())
