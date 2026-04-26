"""Tests for telegram inbound sticker handling — file_id persistence + injection."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_sticker_persists_file_id_on_first_hit(tmp_path, monkeypatch):
    """A previously-unseen static sticker triggers vision and stores file_id."""
    cache_file = tmp_path / "cache.json"

    # Build a fake static Sticker
    sticker = MagicMock()
    sticker.file_unique_id = "uid_new"
    sticker.file_id = "FILEID_NEW"
    sticker.emoji = "🐱"
    sticker.set_name = "Cats"
    sticker.is_animated = False
    sticker.is_video = False
    sticker.get_file = AsyncMock()
    file_obj = MagicMock()
    file_obj.download_as_bytearray = AsyncMock(return_value=bytearray(b"fakebytes"))
    sticker.get_file.return_value = file_obj

    msg = MagicMock(); msg.sticker = sticker
    event = MagicMock(); event.text = ""

    from gateway.platforms.telegram import TelegramAdapter
    adapter = TelegramAdapter.__new__(TelegramAdapter)

    # Mock vision to a deterministic result and patch cache path
    fake_vision = AsyncMock(return_value=json.dumps({"success": True, "analysis": "A cat"}))
    with patch("gateway.sticker_cache.CACHE_PATH", cache_file), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision), \
         patch("gateway.platforms.telegram.cache_image_from_bytes", return_value="/tmp/fake.webp"):
        await adapter._handle_sticker(msg, event)

    cache = json.loads(cache_file.read_text())
    assert cache["uid_new"]["file_id"] == "FILEID_NEW"
    assert cache["uid_new"]["description"] == "A cat"


@pytest.mark.asyncio
async def test_handle_sticker_backfills_legacy_entry_without_revision(tmp_path):
    """A legacy entry (description but no file_id) backfills file_id and skips vision."""
    cache_file = tmp_path / "cache.json"
    legacy = {
        "uid_legacy": {
            "description": "A pre-upgrade panda",
            "emoji": "🐼",
            "set_name": "Pandas",
            "cached_at": 1.0,
            # no file_id
        }
    }
    cache_file.write_text(json.dumps(legacy))

    sticker = MagicMock()
    sticker.file_unique_id = "uid_legacy"
    sticker.file_id = "NEW_FILEID_FOR_LEGACY"
    sticker.emoji = "🐼"
    sticker.set_name = "Pandas"
    sticker.is_animated = False
    sticker.is_video = False
    msg = MagicMock(); msg.sticker = sticker
    event = MagicMock(); event.text = ""

    from gateway.platforms.telegram import TelegramAdapter
    adapter = TelegramAdapter.__new__(TelegramAdapter)

    fake_vision = AsyncMock()  # would raise AssertionError if invoked
    with patch("gateway.sticker_cache.CACHE_PATH", cache_file), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision):
        await adapter._handle_sticker(msg, event)

    fake_vision.assert_not_called()
    cache = json.loads(cache_file.read_text())
    assert cache["uid_legacy"]["file_id"] == "NEW_FILEID_FOR_LEGACY"
    # Existing description preserved
    assert cache["uid_legacy"]["description"] == "A pre-upgrade panda"


@pytest.mark.asyncio
async def test_handle_sticker_injection_text_includes_file_unique_id(tmp_path):
    """Agent-facing injection text includes (id: ...) so the agent can reference the sticker."""
    cache_file = tmp_path / "cache.json"
    cached = {
        "uid_visible": {
            "description": "A cat waving",
            "emoji": "👋",
            "set_name": "Cats",
            "cached_at": 1.0,
            "file_id": "FILEID_VISIBLE",
        }
    }
    cache_file.write_text(json.dumps(cached))

    sticker = MagicMock()
    sticker.file_unique_id = "uid_visible"
    sticker.file_id = "FILEID_VISIBLE"
    sticker.emoji = "👋"
    sticker.set_name = "Cats"
    sticker.is_animated = False
    sticker.is_video = False
    msg = MagicMock(); msg.sticker = sticker
    event = MagicMock(); event.text = ""

    from gateway.platforms.telegram import TelegramAdapter
    adapter = TelegramAdapter.__new__(TelegramAdapter)
    with patch("gateway.sticker_cache.CACHE_PATH", cache_file):
        await adapter._handle_sticker(msg, event)

    assert "uid_visible" in event.text  # id is referenceable
    assert "A cat waving" in event.text
