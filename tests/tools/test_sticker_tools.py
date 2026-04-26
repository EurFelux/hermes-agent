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
    assert "hasn't been registered" in result["error"]


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
    assert "hasn't been registered" in result["error"]


@pytest.mark.asyncio
async def test_edit_sticker_updates_named_fields(patched_paths):
    from gateway.sticker_library import add_sticker
    add_sticker("uid_x", "F_X", "old desc", "old notes")

    from tools.sticker_tools import edit_sticker_handler
    result = json.loads(await edit_sticker_handler({
        "file_unique_id": "uid_x",
        "description": "new desc",
        # usage_notes intentionally omitted
    }))
    assert result["success"] is True

    from gateway.sticker_library import get_sticker
    entry = get_sticker("uid_x")
    assert entry["description"] == "new desc"
    assert entry["usage_notes"] == "old notes"  # untouched


@pytest.mark.asyncio
async def test_edit_sticker_missing_returns_error(patched_paths):
    from tools.sticker_tools import edit_sticker_handler
    result = json.loads(await edit_sticker_handler({
        "file_unique_id": "uid_missing", "description": "x",
    }))
    assert result["success"] is False
    assert "not in your library" in result["error"].lower()


@pytest.mark.asyncio
async def test_remove_from_library_existing(patched_paths):
    from gateway.sticker_library import add_sticker, get_sticker
    add_sticker("uid_x", "F_X", "desc", "")

    from tools.sticker_tools import remove_from_library_handler
    result = json.loads(await remove_from_library_handler({"file_unique_id": "uid_x"}))
    assert result["success"] is True
    assert get_sticker("uid_x") is None


@pytest.mark.asyncio
async def test_remove_from_library_missing_is_success(patched_paths):
    """Removing a non-existent entry is a no-op success (idempotent)."""
    from tools.sticker_tools import remove_from_library_handler
    result = json.loads(await remove_from_library_handler({"file_unique_id": "uid_nope"}))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_add_set_to_library_happy_path(patched_paths):
    """A pack with two static stickers (one already cached, one new) is fully added."""
    from gateway.sticker_cache import cache_sticker_description
    # Pre-cache uid_known so vision should NOT be re-run for it
    cache_sticker_description("uid_known", "A known cat", emoji="🐱", set_name="MyPack", file_id="F_KNOWN")

    sticker_known = MagicMock()
    sticker_known.file_unique_id = "uid_known"
    sticker_known.file_id = "F_KNOWN"
    sticker_known.emoji = "🐱"
    sticker_known.set_name = "MyPack"
    sticker_known.is_animated = False
    sticker_known.is_video = False
    sticker_known.get_file = AsyncMock()  # would be called only on cache miss

    sticker_new = MagicMock()
    sticker_new.file_unique_id = "uid_new"
    sticker_new.file_id = "F_NEW"
    sticker_new.emoji = "🐶"
    sticker_new.set_name = "MyPack"
    sticker_new.is_animated = False
    sticker_new.is_video = False
    new_file_obj = MagicMock()
    new_file_obj.download_as_bytearray = AsyncMock(return_value=bytearray(b"bytes"))
    sticker_new.get_file = AsyncMock(return_value=new_file_obj)

    fake_set = MagicMock()
    fake_set.stickers = [sticker_known, sticker_new]
    fake_bot = MagicMock()
    fake_bot.get_sticker_set = AsyncMock(return_value=fake_set)

    fake_vision = AsyncMock(return_value=json.dumps({"success": True, "analysis": "A new dog"}))

    with patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision), \
         patch("tools.sticker_tools.cache_image_from_bytes", return_value="/tmp/fake.webp"):
        from tools.sticker_tools import add_set_to_library_handler
        result = json.loads(await add_set_to_library_handler({"set_name": "MyPack"}))

    assert result["success"] is True
    assert result["added"] == 2
    assert result["skipped"] == 0

    from gateway.sticker_library import get_sticker
    assert get_sticker("uid_known")["description"] == "A known cat"  # cache reused
    assert get_sticker("uid_new")["description"] == "A new dog"      # vision-derived
    fake_vision.assert_awaited_once()  # only the new one


@pytest.mark.asyncio
async def test_add_set_to_library_skips_animated_and_video(patched_paths):
    sticker_anim = MagicMock(file_unique_id="uid_a", file_id="FA", emoji="", set_name="P",
                             is_animated=True, is_video=False)
    sticker_video = MagicMock(file_unique_id="uid_v", file_id="FV", emoji="", set_name="P",
                              is_animated=False, is_video=True)
    sticker_static = MagicMock(file_unique_id="uid_s", file_id="FS", emoji="", set_name="P",
                               is_animated=False, is_video=False)
    static_file = MagicMock()
    static_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"x"))
    sticker_static.get_file = AsyncMock(return_value=static_file)

    fake_set = MagicMock(); fake_set.stickers = [sticker_anim, sticker_video, sticker_static]
    fake_bot = MagicMock(); fake_bot.get_sticker_set = AsyncMock(return_value=fake_set)
    fake_vision = AsyncMock(return_value=json.dumps({"success": True, "analysis": "static one"}))

    with patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision), \
         patch("tools.sticker_tools.cache_image_from_bytes", return_value="/tmp/fake.webp"):
        from tools.sticker_tools import add_set_to_library_handler
        result = json.loads(await add_set_to_library_handler({"set_name": "P"}))

    assert result["added"] == 1
    assert result["skipped"] == 2

    from gateway.sticker_library import get_sticker
    assert get_sticker("uid_s") is not None
    assert get_sticker("uid_a") is None
    assert get_sticker("uid_v") is None


@pytest.mark.asyncio
async def test_add_set_to_library_caches_with_fallback_on_vision_failure(patched_paths):
    """Vision failure still caches the file_id (with a fallback description) so
    add_sticker_to_library can find it later. Sticker library must remain
    usable when vision is misconfigured — users can fix descriptions via
    edit_sticker."""
    cache_path, _library_path = patched_paths

    sticker_fail = MagicMock(
        file_unique_id="uid_fail", file_id="F_FAIL",
        emoji="😺", set_name="MyPack",
        is_animated=False, is_video=False,
    )
    file_obj = MagicMock()
    file_obj.download_as_bytearray = AsyncMock(return_value=bytearray(b"x"))
    sticker_fail.get_file = AsyncMock(return_value=file_obj)

    fake_set = MagicMock(); fake_set.stickers = [sticker_fail]
    fake_bot = MagicMock(); fake_bot.get_sticker_set = AsyncMock(return_value=fake_set)
    fake_vision = AsyncMock(return_value=json.dumps({"success": False, "error": "vision down"}))

    with patch("tools.sticker_tools._build_bot", return_value=fake_bot), \
         patch("tools.vision_tools.vision_analyze_tool", fake_vision), \
         patch("tools.sticker_tools.cache_image_from_bytes", return_value="/tmp/x.webp"):
        from tools.sticker_tools import add_set_to_library_handler
        result = json.loads(await add_set_to_library_handler({"set_name": "MyPack"}))

    # Library gets the entry with fallback description.
    assert result["added"] == 1
    from gateway.sticker_library import get_sticker
    entry = get_sticker("uid_fail")
    assert entry is not None
    assert entry["file_id"] == "F_FAIL"
    assert "emoji" in entry["description"].lower() or "sticker" in entry["description"].lower()

    # Cache also gets the file_id + fallback description so future cache hits
    # don't have to retry vision and add_sticker_to_library can resolve file_id.
    cache = json.loads(cache_path.read_text())
    assert cache["uid_fail"]["file_id"] == "F_FAIL"
    assert cache["uid_fail"]["description"]  # non-empty fallback
