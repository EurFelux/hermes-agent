"""Test that sticker tools are bundled into the hermes-telegram toolset."""


def test_hermes_telegram_includes_sticker_tools():
    from toolsets import TOOLSETS
    tg = TOOLSETS["hermes-telegram"]
    expected = {
        "send_sticker",
        "list_my_stickers",
        "add_sticker_to_library",
        "add_set_to_library",
        "edit_sticker",
        "remove_from_library",
    }
    missing = expected - set(tg["tools"])
    assert not missing, f"hermes-telegram missing sticker tools: {missing}"
