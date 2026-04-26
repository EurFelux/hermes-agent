"""End-to-end mocked test: inbound sticker → add to library → send_sticker dispatches correctly."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_inbound_then_add_then_send(tmp_path):
    cache_path = tmp_path / "cache.json"
    library_path = tmp_path / "library.json"

    # 1. Receive a static sticker via the adapter
    sticker = MagicMock(
        file_unique_id="uid_e2e",
        file_id="FILEID_E2E",
        emoji="🐱",
        set_name="E2E",
        is_animated=False,
        is_video=False,
    )
    file_obj = MagicMock()
    file_obj.download_as_bytearray = AsyncMock(return_value=bytearray(b"x"))
    sticker.get_file = AsyncMock(return_value=file_obj)

    msg = MagicMock(); msg.sticker = sticker
    event = MagicMock(); event.text = ""

    from gateway.platforms.telegram import TelegramAdapter
    adapter = TelegramAdapter.__new__(TelegramAdapter)

    fake_vision = AsyncMock(return_value=json.dumps({"success": True, "analysis": "An e2e cat"}))
    with patch("gateway.sticker_cache.CACHE_PATH", cache_path), \
         patch("gateway.sticker_library.LIBRARY_PATH", library_path), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision), \
         patch("gateway.platforms.telegram.cache_image_from_bytes", return_value="/tmp/x.webp"):
        await adapter._handle_sticker(msg, event)

    # Cache now contains uid_e2e with file_id
    cache = json.loads(cache_path.read_text())
    assert cache["uid_e2e"]["file_id"] == "FILEID_E2E"
    # Injection text is referenceable
    assert "uid_e2e" in event.text

    # 2. Agent calls add_sticker_to_library
    with patch("gateway.sticker_cache.CACHE_PATH", cache_path), \
         patch("gateway.sticker_library.LIBRARY_PATH", library_path):
        from tools.sticker_tools import add_sticker_to_library_handler
        add_result = json.loads(await add_sticker_to_library_handler({
            "file_unique_id": "uid_e2e",
            "usage_notes": "test",
        }))
    assert add_result["success"] is True

    # 3. Agent calls send_sticker — bot.send_sticker is invoked with FILEID_E2E
    fake_bot = MagicMock(); fake_bot.send_sticker = AsyncMock(return_value=MagicMock(message_id=42))
    with patch("gateway.sticker_cache.CACHE_PATH", cache_path), \
         patch("gateway.sticker_library.LIBRARY_PATH", library_path), \
         patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.sticker_tools._current_chat_id", return_value="555"):
        from tools.sticker_tools import send_sticker_handler
        send_result = json.loads(await send_sticker_handler({"file_unique_id": "uid_e2e"}))

    assert send_result["success"] is True
    fake_bot.send_sticker.assert_awaited_once()
    args, kwargs = fake_bot.send_sticker.call_args
    assert kwargs.get("sticker", args[1] if len(args) > 1 else None) == "FILEID_E2E"
    assert str(kwargs.get("chat_id", args[0] if args else None)) == "555"
