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


@pytest.mark.asyncio
async def test_list_my_stickers_returns_entries(patched_paths):
    from gateway.sticker_library import add_sticker
    add_sticker("uid_a", "FA", "A cat", "greetings")
    add_sticker("uid_b", "FB", "A panda", "")

    from tools.sticker_tools import list_my_stickers_handler
    result = json.loads(await list_my_stickers_handler({}))
    assert result["success"] is True
    ids = {s["file_unique_id"] for s in result["stickers"]}
    assert ids == {"uid_a", "uid_b"}
    # file_id must NOT leak into agent-visible output
    assert all("file_id" not in s for s in result["stickers"])


@pytest.mark.asyncio
async def test_list_my_stickers_empty(patched_paths):
    from tools.sticker_tools import list_my_stickers_handler
    result = json.loads(await list_my_stickers_handler({}))
    assert result["success"] is True
    assert result["stickers"] == []


def test_dispatch_async_sticker_tools_returns_json_string(patched_paths):
    """
    Regression: every async sticker tool MUST register with is_async=True.
    Without it, registry.dispatch() returns an unawaited coroutine instead of
    a JSON string, breaking the live agent.
    """
    import json as _json
    from gateway.sticker_library import add_sticker
    add_sticker("uid_d", "FD", "A dispatch test sticker", "")

    # Force registration; otherwise this test depends on import side-effects
    # from sibling tests (which fail under pytest-xdist or in-isolation runs).
    import tools.sticker_tools  # noqa: F401

    from tools.registry import registry
    # Trigger dispatch — if is_async is missing, this returns a coroutine, not str.
    out = registry.dispatch("list_my_stickers", {})
    assert isinstance(out, str), (
        f"list_my_stickers dispatch returned {type(out).__name__}, not str — "
        "is_async flag likely missing from registry.register"
    )
    payload = _json.loads(out)
    assert payload["success"] is True
    assert any(s["file_unique_id"] == "uid_d" for s in payload["stickers"])


@pytest.mark.asyncio
async def test_add_sticker_to_library_happy_path(patched_paths):
    from gateway.sticker_cache import cache_sticker_description
    cache_sticker_description("uid_x", "A waving cat", emoji="👋", set_name="Cats", file_id="F_X")

    from tools.sticker_tools import add_sticker_to_library_handler
    result = json.loads(await add_sticker_to_library_handler({"file_unique_id": "uid_x"}))
    assert result["success"] is True

    from gateway.sticker_library import get_sticker
    entry = get_sticker("uid_x")
    assert entry["file_id"] == "F_X"
    assert entry["description"] == "A waving cat"
    assert entry["usage_notes"] == ""


@pytest.mark.asyncio
async def test_add_sticker_to_library_with_overrides(patched_paths):
    from gateway.sticker_cache import cache_sticker_description
    cache_sticker_description("uid_x", "Default desc", file_id="F_X")

    from tools.sticker_tools import add_sticker_to_library_handler
    args = {
        "file_unique_id": "uid_x",
        "description": "Custom desc",
        "usage_notes": "Use for hellos",
    }
    result = json.loads(await add_sticker_to_library_handler(args))
    assert result["success"] is True

    from gateway.sticker_library import get_sticker
    entry = get_sticker("uid_x")
    assert entry["description"] == "Custom desc"
    assert entry["usage_notes"] == "Use for hellos"


@pytest.mark.asyncio
async def test_add_sticker_to_library_cache_miss(patched_paths):
    from tools.sticker_tools import add_sticker_to_library_handler
    result = json.loads(await add_sticker_to_library_handler({"file_unique_id": "uid_unknown"}))
    assert result["success"] is False
    assert "hasn't been received" in result["error"]


@pytest.mark.asyncio
async def test_add_sticker_to_library_legacy_entry_no_file_id(patched_paths):
    """Cache entry exists but lacks file_id → actionable error directing the user to resend."""
    cache_path, _ = patched_paths
    legacy = {
        "uid_legacy": {
            "description": "An old sticker",
            "emoji": "",
            "set_name": "",
            "cached_at": 1.0,
            # no file_id
        }
    }
    cache_path.write_text(json.dumps(legacy))

    from tools.sticker_tools import add_sticker_to_library_handler
    result = json.loads(await add_sticker_to_library_handler({"file_unique_id": "uid_legacy"}))
    assert result["success"] is False
    assert "send it again" in result["error"].lower()
