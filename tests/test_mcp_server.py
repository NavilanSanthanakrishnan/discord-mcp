from pathlib import Path

import pytest

from discord_user_mcp.mcp_server import _lifespan, create_mcp
from tests.test_runtime import make_runtime


@pytest.mark.asyncio
async def test_mcp_registers_expected_tools(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        mcp = create_mcp(runtime=runtime)
        tool_names = {tool.name for tool in await mcp.list_tools()}
        assert {
            "discord_status",
            "get_custom_status",
            "set_custom_status",
            "list_dms",
            "list_servers",
            "list_server_channels",
            "read_messages",
            "send_message",
            "send_natural_message",
            "reply_to_message",
            "edit_message",
            "delete_message",
            "add_reaction",
            "remove_reaction",
            "send_typing_indicator",
            "send_attachments",
            "poll_new_dm_events",
            "collect_dm_burst",
            "start_dm_watch",
            "poll_active_dm",
            "stop_dm_watch",
        } <= tool_names
        assert "send_dm" not in tool_names
        assert "send_channel_message" not in tool_names
    finally:
        runtime.store.close()


@pytest.mark.asyncio
async def test_lifespan_keeps_runtime_open_between_http_sessions(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        async with _lifespan(runtime):
            pass

        assert runtime.rest.closed is False
        assert runtime.store.list_dm_channels() == []
    finally:
        await runtime.close()
