"""Tests for sticker section appended to build_session_context_prompt on Telegram."""

from unittest.mock import patch
from types import SimpleNamespace

import pytest


def _make_telegram_context(tmp_path):
    """Construct a minimal SessionContext-like object that build_session_context_prompt accepts."""
    from gateway.config import Platform
    from gateway.session import SessionContext, SessionSource

    src = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="123",
        chat_type="dm",
        user_id="user1",
        user_name="Alice",
    )
    return SessionContext(
        source=src,
        connected_platforms=[Platform.TELEGRAM],
        home_channels={},
        shared_multi_user_session=False,
    )


def test_telegram_with_non_empty_library_includes_section(tmp_path):
    library = tmp_path / "library.json"
    with patch("gateway.sticker_library.LIBRARY_PATH", library):
        from gateway.sticker_library import add_sticker
        add_sticker("uid_x", "F_x", "A waving cat", "greetings")
        from gateway.session import build_session_context_prompt
        ctx = _make_telegram_context(tmp_path)
        prompt = build_session_context_prompt(ctx)
    assert "## Sticker Library" in prompt
    assert "uid_x" in prompt


def test_telegram_with_empty_library_omits_section(tmp_path):
    library = tmp_path / "library.json"  # never written → empty
    with patch("gateway.sticker_library.LIBRARY_PATH", library):
        from gateway.session import build_session_context_prompt
        ctx = _make_telegram_context(tmp_path)
        prompt = build_session_context_prompt(ctx)
    assert "## Sticker Library" not in prompt


def test_non_telegram_platform_omits_section(tmp_path):
    """Even with a non-empty library, non-Telegram sessions don't get the section."""
    library = tmp_path / "library.json"
    with patch("gateway.sticker_library.LIBRARY_PATH", library):
        from gateway.sticker_library import add_sticker
        add_sticker("uid_x", "F_x", "A cat", "")
        from gateway.config import Platform
        from gateway.session import SessionContext, SessionSource, build_session_context_prompt
        src = SessionSource(
            platform=Platform.DISCORD,
            chat_id="123",
            chat_type="dm",
            user_id="u",
            user_name="A",
        )
        ctx = SessionContext(
            source=src,
            connected_platforms=[Platform.DISCORD],
            home_channels={},
            shared_multi_user_session=False,
        )
        prompt = build_session_context_prompt(ctx)
    assert "## Sticker Library" not in prompt
