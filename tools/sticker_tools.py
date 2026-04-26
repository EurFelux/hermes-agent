"""
Sticker tools — agent-facing operations on the sticker library.

Six tools register here: send_sticker, list_my_stickers, add_sticker_to_library,
add_set_to_library, edit_sticker, remove_from_library. They are bundled into
the hermes-telegram toolset via toolsets.py once all six tools are registered.

Bot/chat resolution: like ``tools/send_message_tool.py``, these tools build a
short-lived ``telegram.Bot`` from ``TELEGRAM_BOT_TOKEN`` for each call. The
target chat_id is read from the gateway's session context (set per-message in
``gateway/run.py``). Tools fail with a clear error if invoked outside a gateway
chat session (e.g. raw CLI use).
"""

import json
import logging
import os
from typing import Optional

from tools.registry import registry, tool_error  # noqa: F401 — tool_error used by Tasks 6-10

logger = logging.getLogger(__name__)


def _build_bot():
    """Construct a one-shot PTB Bot instance from TELEGRAM_BOT_TOKEN."""
    from telegram import Bot
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return Bot(token=token)


def _current_chat_id() -> Optional[str]:
    """Read the current chat_id from gateway session env (None if not in a chat)."""
    from gateway.session_context import get_session_env
    chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
    return chat_id or None


def _err(msg: str) -> str:
    return json.dumps({"success": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict) -> str:
    return json.dumps({"success": True, **payload}, ensure_ascii=False)


# --------- send_sticker ---------

SEND_STICKER_SCHEMA = {
    "name": "send_sticker",
    "description": (
        "Send a sticker from your sticker library to the current chat. Use this "
        "when a sticker fits the moment naturally — e.g. the user shared a sticker "
        "and you want to respond in kind, or the moment calls for the kind of "
        "expression a sticker captures. The file_unique_id must be one from your "
        "library; call list_my_stickers if you're not sure what you have."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_unique_id": {
                "type": "string",
                "description": "Stable identifier of a sticker already in your library.",
            },
        },
        "required": ["file_unique_id"],
    },
}


async def send_sticker_handler(args: dict, **_) -> str:
    file_unique_id = args.get("file_unique_id", "")
    if not file_unique_id:
        return _err("file_unique_id is required")

    from gateway.sticker_library import get_sticker
    entry = get_sticker(file_unique_id)
    if not entry:
        return _err(f"Sticker {file_unique_id!r} is not in your library")

    chat_id = _current_chat_id()
    if not chat_id:
        return _err("send_sticker can only run inside a gateway chat session")

    try:
        bot = _build_bot()
    except RuntimeError as e:
        return _err(str(e))

    from telegram.error import BadRequest
    try:
        msg = await bot.send_sticker(chat_id=int(chat_id), sticker=entry["file_id"])
    except BadRequest as e:
        err_lc = str(e).lower()
        if (
            "file_id_invalid" in err_lc
            or "wrong file" in err_lc          # catches "wrong file_id" and "wrong file id"
            or "wrong remote file" in err_lc
            or "file_id is invalid" in err_lc
            or "invalid file id" in err_lc     # keep as catch-all in case PTB normalizes
        ):
            return _err(
                "Sticker is no longer accessible (invalid file id). "
                "You can call remove_from_library to drop it."
            )
        return _err(f"Telegram rejected the sticker: {e}")
    except Exception as e:
        return _err(f"Failed to send sticker: {e}")

    return _ok({
        "platform": "telegram",
        "chat_id": chat_id,
        "file_unique_id": file_unique_id,
        "message_id": getattr(msg, "message_id", None),
    })


registry.register(
    name="send_sticker",
    toolset="messaging",
    schema=SEND_STICKER_SCHEMA,
    handler=send_sticker_handler,
    emoji="🎟️",
)
