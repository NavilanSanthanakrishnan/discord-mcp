from __future__ import annotations

from discord_user_mcp.config import Settings
from discord_user_mcp.mcp_server import create_mcp


def main() -> None:
    settings = Settings.from_env()
    create_mcp(settings).run(transport="streamable-http")


if __name__ == "__main__":
    main()
