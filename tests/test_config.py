from pathlib import Path

import pytest

from discord_user_mcp.config import ConfigError, Settings, redact_token


def test_read_token_uses_first_line(tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("abc123\nignored\n", encoding="utf-8")

    assert Settings(token_file=token_file).read_token() == "abc123"


def test_read_token_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Settings(token_file=tmp_path / "missing.txt").read_token()


def test_redact_token() -> None:
    assert redact_token("1234567890") == "1234...7890"
    assert redact_token("short") == "<redacted>"
