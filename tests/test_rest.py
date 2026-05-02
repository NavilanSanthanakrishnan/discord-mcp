import json
from datetime import UTC, datetime

import httpx
import pytest

from discord_user_mcp.discord.rest import DiscordRestClient


@pytest.mark.asyncio
async def test_list_dm_channels_filters_and_sends_raw_auth_header() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "dm1",
                    "type": 1,
                    "recipients": [{"id": "u1", "username": "purplecerd"}],
                    "last_message_id": "m1",
                },
                {"id": "guild-text", "type": 0, "name": "general"},
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordRestClient(
            "user-token",
            base_url="https://discord.test/api/v9",
            client=http_client,
        )
        channels = await client.list_dm_channels()

    assert [channel.id for channel in channels] == ["dm1"]
    assert channels[0].name == "purplecerd"
    assert seen_requests[0].headers["Authorization"] == "user-token"
    assert str(seen_requests[0].url) == "https://discord.test/api/v9/users/@me/channels"


@pytest.mark.asyncio
async def test_read_messages_builds_cursor_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://discord.test/api/v9/channels/dm1/messages?limit=5&after=123"
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": "456",
                    "channel_id": "dm1",
                    "content": "hello",
                    "timestamp": "2026-05-01T00:00:00+00:00",
                    "author": {"id": "u1", "username": "purplecerd"},
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordRestClient(
            "token",
            base_url="https://discord.test/api/v9",
            client=http_client,
        )
        messages = await client.read_messages("dm1", limit=5, after="123")

    assert messages[0].content == "hello"
    assert messages[0].timestamp == datetime(2026, 5, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_send_message_posts_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert json.loads(request.content) == {"content": "hello back"}
        return httpx.Response(
            200,
            json={
                "id": "789",
                "channel_id": "dm1",
                "content": "hello back",
                "timestamp": "2026-05-01T00:00:01+00:00",
                "author": {"id": "me", "username": "me"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordRestClient(
            "token",
            base_url="https://discord.test/api/v9",
            client=http_client,
        )
        message = await client.send_message("dm1", "hello back")

    assert message.id == "789"
    assert message.content == "hello back"


@pytest.mark.asyncio
async def test_edit_delete_and_typing_endpoints() -> None:
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path.endswith("/typing"):
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "id": "789",
                "channel_id": "dm1",
                "content": "edited",
                "timestamp": "2026-05-01T00:00:01+00:00",
                "author": {"id": "me", "username": "me"},
                "edited_timestamp": "2026-05-01T00:00:02+00:00",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordRestClient(
            "token",
            base_url="https://discord.test/api/v9",
            client=http_client,
        )
        edited = await client.edit_message("dm1", "789", "edited")
        await client.delete_message("dm1", "789")
        await client.send_typing_indicator("dm1")

    assert edited.content == "edited"
    assert seen == [
        (
            "PATCH",
            "/api/v9/channels/dm1/messages/789",
            b'{"content":"edited"}',
        ),
        ("DELETE", "/api/v9/channels/dm1/messages/789", b""),
        ("POST", "/api/v9/channels/dm1/typing", b""),
    ]


@pytest.mark.asyncio
async def test_send_message_with_attachments_uses_multipart(tmp_path) -> None:
    attachment = tmp_path / "note.txt"
    attachment.write_text("hello file", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v9/channels/dm1/messages"
        assert "multipart/form-data" in request.headers["Content-Type"]
        body = request.content
        assert b'name="payload_json"' in body
        assert b'name="files[0]"; filename="note.txt"' in body
        return httpx.Response(
            200,
            json={
                "id": "790",
                "channel_id": "dm1",
                "content": "with file",
                "timestamp": "2026-05-01T00:00:01+00:00",
                "author": {"id": "me", "username": "me"},
                "attachments": [{"id": "a1", "filename": "note.txt"}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordRestClient(
            "token",
            base_url="https://discord.test/api/v9",
            client=http_client,
        )
        message = await client.send_message_with_attachments(
            "dm1",
            content="with file",
            attachment_paths=[str(attachment)],
        )

    assert message.id == "790"
    assert message.raw["attachments"][0]["filename"] == "note.txt"
