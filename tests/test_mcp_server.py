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
            "discord_api_request",
            "get_current_user",
            "get_current_bot",
            "get_bot_invite_url",
            "get_custom_status",
            "set_custom_status",
            "list_relationships",
            "list_message_requests",
            "poll_message_requests",
            "accept_message_request",
            "delete_relationship",
            "get_user_profile",
            "ack_message",
            "list_dms",
            "create_dm_channel",
            "send_private_message",
            "read_private_messages",
            "edit_private_message",
            "delete_private_message",
            "list_servers",
            "list_server_channels",
            "get_server_info",
            "list_all_server_channels",
            "list_channels",
            "create_text_channel",
            "create_voice_channel",
            "create_stage_channel",
            "create_category",
            "create_server",
            "create_server_from_template",
            "get_server_preview",
            "list_server_voice_regions",
            "get_server_vanity_url",
            "get_server_widget",
            "get_server_widget_json",
            "edit_server_widget",
            "get_welcome_screen",
            "edit_welcome_screen",
            "get_server_onboarding",
            "edit_server_onboarding",
            "leave_server",
            "edit_forum_channel",
            "get_channel_info",
            "find_channel",
            "find_category",
            "list_channels_in_category",
            "move_channel",
            "list_channel_permission_overwrites",
            "upsert_channel_permission_overwrite",
            "upsert_role_channel_permissions",
            "upsert_member_channel_permissions",
            "delete_channel_permission_overwrite",
            "list_forum_channels",
            "get_forum_channel_info",
            "list_forum_tags",
            "create_forum_post",
            "list_forum_posts",
            "modify_forum_post",
            "edit_channel",
            "edit_text_channel",
            "edit_voice_channel",
            "edit_category",
            "delete_channel",
            "delete_category",
            "read_messages",
            "send_message",
            "send_natural_message",
            "reply_to_message",
            "edit_message",
            "delete_message",
            "pin_message",
            "bulk_delete_messages",
            "get_message",
            "get_attachment",
            "add_reaction",
            "remove_reaction",
            "send_typing_indicator",
            "send_attachments",
            "list_roles",
            "create_role",
            "get_member",
            "get_member_info",
            "get_user_id_by_name",
            "add_member_to_server",
            "list_member_roles",
            "set_nickname",
            "move_member",
            "disconnect_member",
            "modify_voice_state",
            "timeout_member",
            "get_bans",
            "list_guild_scheduled_events",
            "create_guild_scheduled_event",
            "get_guild_scheduled_event",
            "edit_guild_scheduled_event",
            "delete_guild_scheduled_event",
            "get_guild_scheduled_event_users",
            "create_invite",
            "get_invite_details",
            "list_invites",
            "get_guild_template",
            "list_emojis",
            "get_emoji",
            "get_emoji_details",
            "create_emoji",
            "edit_emoji",
            "delete_emoji",
            "create_webhook",
            "list_webhooks",
            "get_webhook",
            "send_webhook_message",
            "get_server_blueprint_schema",
            "apply_server_blueprint",
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
