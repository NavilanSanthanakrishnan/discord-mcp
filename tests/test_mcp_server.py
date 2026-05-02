from pathlib import Path

import pytest

from discord_user_mcp.mcp_server import create_mcp
from tests.test_runtime import make_runtime


@pytest.mark.asyncio
async def test_mcp_registers_expected_tools(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    try:
        mcp = create_mcp(runtime=runtime)
        tool_names = {tool.name for tool in await mcp.list_tools()}
        assert {
            "discord_status",
            "list_dms",
            "read_dm",
            "send_dm",
            "poll_new_dm_events",
            "start_dm_watch",
            "poll_active_dm",
            "stop_dm_watch",
        } <= tool_names
    finally:
        runtime.store.close()
