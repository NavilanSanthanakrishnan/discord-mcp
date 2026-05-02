from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOKEN_FILE = Path("/Users/navilan/Documents/DiscordMCP/token.txt")
DEFAULT_DB_PATH = Path("/Users/navilan/Documents/DiscordMCP/.local/discord_user_mcp.sqlite")


class ConfigError(RuntimeError):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    token_file: Path = DEFAULT_TOKEN_FILE
    db_path: Path = DEFAULT_DB_PATH
    discord_api_base: str = "https://discord.com/api/v9"
    discord_gateway_url: str = "wss://gateway.discord.gg/?v=9&encoding=json"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8085
    allow_send: bool = True
    natural_typing_wpm: int = 55
    natural_typing_min_seconds: float = 1.0
    natural_typing_max_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            token_file=Path(os.getenv("DISCORD_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))),
            db_path=Path(os.getenv("DISCORD_MCP_DB", str(DEFAULT_DB_PATH))),
            discord_api_base=os.getenv("DISCORD_API_BASE", "https://discord.com/api/v9").rstrip("/"),
            discord_gateway_url=os.getenv(
                "DISCORD_GATEWAY_URL", "wss://gateway.discord.gg/?v=9&encoding=json"
            ),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.getenv("MCP_PORT", "8085")),
            allow_send=os.getenv("ALLOW_SEND", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            natural_typing_wpm=int(os.getenv("NATURAL_TYPING_WPM", "55")),
            natural_typing_min_seconds=float(os.getenv("NATURAL_TYPING_MIN_SECONDS", "1.0")),
            natural_typing_max_seconds=float(os.getenv("NATURAL_TYPING_MAX_SECONDS", "20.0")),
        )

    def read_token(self) -> str:
        try:
            first_line = self.token_file.read_text(encoding="utf-8").splitlines()[0]
        except FileNotFoundError as exc:
            raise ConfigError(f"Discord token file not found: {self.token_file}") from exc
        except IndexError as exc:
            raise ConfigError(f"Discord token file is empty: {self.token_file}") from exc

        token = first_line.strip()
        if not token:
            raise ConfigError(f"Discord token file first line is blank: {self.token_file}")
        return token


def redact_token(token: str) -> str:
    if len(token) <= 8:
        return "<redacted>"
    return f"{token[:4]}...{token[-4:]}"
