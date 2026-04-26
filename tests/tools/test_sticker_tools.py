"""Tests for tools/sticker_tools.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def patched_paths(tmp_path):
    """Redirect both cache and library to per-test temp files."""
    cache = tmp_path / "cache.json"
    library = tmp_path / "library.json"
    with patch("gateway.sticker_cache.CACHE_PATH", cache), \
         patch("gateway.sticker_library.LIBRARY_PATH", library):
        yield cache, library


@pytest.mark.asyncio
async def test_send_sticker_happy_path(patched_paths):
    """A library entry exists; bot.send_sticker is called with its file_id."""
    _cache, _library = patched_paths
    from gateway.sticker_library import add_sticker
    add_sticker("uid_1", "FILE_1", "A cat", "greetings")

    fake_bot = MagicMock()
    fake_bot.send_sticker = AsyncMock(return_value=MagicMock(message_id=42))

    with patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.sticker_tools._current_chat_id", return_value="999"):
        from tools.sticker_tools import send_sticker_handler
        result_json = await send_sticker_handler({"file_unique_id": "uid_1"})

    result = json.loads(result_json)
    assert result["success"] is True
    fake_bot.send_sticker.assert_awaited_once()
    args, kwargs = fake_bot.send_sticker.call_args
    # chat_id and file_id passed (positional or keyword — accept either)
    called_chat_id = kwargs.get("chat_id", args[0] if args else None)
    called_file_id = kwargs.get("sticker", args[1] if len(args) > 1 else None)
    assert str(called_chat_id) == "999"
    assert called_file_id == "FILE_1"


@pytest.mark.asyncio
async def test_send_sticker_not_in_library(patched_paths):
    with patch("tools.sticker_tools._current_chat_id", return_value="999"):
        from tools.sticker_tools import send_sticker_handler
        result = json.loads(await send_sticker_handler({"file_unique_id": "uid_missing"}))
    assert result["success"] is False
    assert "not in your library" in result["error"].lower()


@pytest.mark.asyncio
async def test_send_sticker_invalid_file_id_returns_actionable_error(patched_paths):
    from telegram.error import BadRequest
    from gateway.sticker_library import add_sticker
    add_sticker("uid_dead", "FILE_DEAD", "stale", "")

    fake_bot = MagicMock()
    fake_bot.send_sticker = AsyncMock(side_effect=BadRequest("file_id_invalid"))

    with patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.sticker_tools._current_chat_id", return_value="999"):
        from tools.sticker_tools import send_sticker_handler
        result = json.loads(await send_sticker_handler({"file_unique_id": "uid_dead"}))

    assert result["success"] is False
    assert "remove_from_library" in result["error"]
