"""Test that the Telegram PLATFORM_HINT mentions sticker tools by name."""

import pytest


def test_telegram_hint_mentions_sticker_tools():
    from agent.prompt_builder import PLATFORM_HINTS
    hint = PLATFORM_HINTS["telegram"]
    for tool in [
        "send_sticker",
        "list_my_stickers",
        "add_sticker_to_library",
        "add_set_to_library",
        "edit_sticker",
        "remove_from_library",
    ]:
        assert tool in hint, f"PLATFORM_HINTS['telegram'] should mention {tool}"


def test_telegram_hint_preserves_existing_markdown_guidance():
    """Regression: existing media/markdown guidance is still there."""
    from agent.prompt_builder import PLATFORM_HINTS
    hint = PLATFORM_HINTS["telegram"]
    assert "Telegram" in hint
    assert "MEDIA:" in hint
    assert "markdown" in hint.lower()
