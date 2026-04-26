"""
Sticker tools — agent-facing operations on the sticker library.

Six tools — send_sticker, list_my_stickers, add_sticker_to_library,
add_set_to_library, edit_sticker, remove_from_library — bundled into the
hermes-telegram toolset via toolsets.py. Each tool is a self-contained
section below, registered at module load via registry.register().

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

from tools.registry import registry
from gateway.platforms.base import cache_image_from_bytes

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
    toolset="stickers",
    schema=SEND_STICKER_SCHEMA,
    handler=send_sticker_handler,
    is_async=True,
    emoji="🎟️",
)

# --------- list_my_stickers ---------

LIST_MY_STICKERS_SCHEMA = {
    "name": "list_my_stickers",
    "description": (
        "List all stickers in your sticker library with their descriptions and any "
        "usage notes you've recorded. Use this before deciding to send a sticker, "
        "or when the user asks what stickers you have. Returns a list of "
        "{file_unique_id, description, usage_notes} entries."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


async def list_my_stickers_handler(args: dict, **_) -> str:
    from gateway.sticker_library import list_stickers
    return _ok({"stickers": list_stickers()})


registry.register(
    name="list_my_stickers",
    toolset="stickers",
    schema=LIST_MY_STICKERS_SCHEMA,
    handler=list_my_stickers_handler,
    is_async=True,
    emoji="📋",
)

# --------- add_sticker_to_library ---------

ADD_STICKER_SCHEMA = {
    "name": "add_sticker_to_library",
    "description": (
        "Add a single sticker to your library. Use this when the user asks you "
        "to remember a specific sticker — typically one they just sent. Get the "
        "file_unique_id from the sticker message they sent (shown as 'id: ...' "
        "in the inbound text). Optionally pass description or usage_notes to "
        "override the defaults."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_unique_id": {
                "type": "string",
                "description": "Stable identifier of the sticker, taken from inbound (id: ...) text.",
            },
            "description": {
                "type": "string",
                "description": "Override for the description; if omitted, uses the cached vision description.",
            },
            "usage_notes": {
                "type": "string",
                "description": "Initial usage notes; defaults to empty (you can fill in later via edit_sticker).",
            },
        },
        "required": ["file_unique_id"],
    },
}


async def add_sticker_to_library_handler(args: dict, **_) -> str:
    file_unique_id = args.get("file_unique_id", "")
    if not file_unique_id:
        return _err("file_unique_id is required")

    from gateway.sticker_cache import get_cached_description
    cached = get_cached_description(file_unique_id)
    if not cached:
        return _err(
            f"No cached entry for {file_unique_id!r}. The sticker hasn't been "
            "received in this profile yet."
        )

    file_id = cached.get("file_id", "")
    if not file_id:
        return _err(
            "This sticker hasn't been seen since the cache was upgraded. "
            "Please send it again so I can register it."
        )

    description = args.get("description")
    if description is None:
        description = cached["description"]
    usage_notes = args.get("usage_notes", "")

    from gateway.sticker_library import add_sticker
    add_sticker(file_unique_id, file_id, description, usage_notes)

    return _ok({"file_unique_id": file_unique_id, "description": description})


registry.register(
    name="add_sticker_to_library",
    toolset="stickers",
    schema=ADD_STICKER_SCHEMA,
    handler=add_sticker_to_library_handler,
    is_async=True,
    emoji="➕",
)

# --------- edit_sticker ---------

EDIT_STICKER_SCHEMA = {
    "name": "edit_sticker",
    "description": (
        "Update fields on a sticker in your library. Use this when the user "
        "tells you when a sticker fits (e.g. 'use this one for greetings'). "
        "Omit any field you don't want to change. To clear `usage_notes`, "
        "pass an empty string. Updates overwrite — to extend usage_notes, "
        "list_my_stickers first to read the current value, merge mentally, "
        "then write back the combined text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_unique_id": {
                "type": "string",
                "description": "Stable identifier of a sticker already in your library.",
            },
            "description": {"type": "string", "description": "New description; omit to leave unchanged."},
            "usage_notes": {"type": "string", "description": "New usage notes; omit to leave unchanged. Empty string clears the field."},
        },
        "required": ["file_unique_id"],
    },
}


async def edit_sticker_handler(args: dict, **_) -> str:
    file_unique_id = args.get("file_unique_id", "")
    if not file_unique_id:
        return _err("file_unique_id is required")

    description = args.get("description") if "description" in args else None
    usage_notes = args.get("usage_notes") if "usage_notes" in args else None

    from gateway.sticker_library import edit_sticker
    try:
        edit_sticker(file_unique_id, description=description, usage_notes=usage_notes)
    except KeyError:
        return _err(f"Sticker {file_unique_id!r} is not in your library")

    return _ok({"file_unique_id": file_unique_id})


registry.register(
    name="edit_sticker",
    toolset="stickers",
    schema=EDIT_STICKER_SCHEMA,
    handler=edit_sticker_handler,
    is_async=True,
    emoji="✏️",
)

# --------- remove_from_library ---------

REMOVE_STICKER_SCHEMA = {
    "name": "remove_from_library",
    "description": (
        "Remove a sticker from your library. Use this when the user asks you "
        "to forget a sticker, or when send_sticker fails with 'invalid file id' "
        "meaning the sticker is no longer accessible."
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


async def remove_from_library_handler(args: dict, **_) -> str:
    file_unique_id = args.get("file_unique_id", "")
    if not file_unique_id:
        return _err("file_unique_id is required")
    from gateway.sticker_library import remove_sticker
    remove_sticker(file_unique_id)
    return _ok({"file_unique_id": file_unique_id})


registry.register(
    name="remove_from_library",
    toolset="stickers",
    schema=REMOVE_STICKER_SCHEMA,
    handler=remove_from_library_handler,
    is_async=True,
    emoji="🗑️",
)

# --------- add_set_to_library ---------

ADD_SET_SCHEMA = {
    "name": "add_set_to_library",
    "description": (
        "Add an entire Telegram sticker pack to your library. Use this when the "
        "user asks you to remember a whole pack (e.g. 'add MyKawaiiPack to your "
        "stickers'). All static stickers in the pack are analyzed and added; "
        "animated and video stickers are skipped (they can't be vision-described). "
        "usage_notes start empty for each."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "set_name": {
                "type": "string",
                "description": "Telegram sticker set name (e.g. 'MyKawaiiPack').",
            },
        },
        "required": ["set_name"],
    },
}


async def add_set_to_library_handler(args: dict, **_) -> str:
    set_name = args.get("set_name", "")
    if not set_name:
        return _err("set_name is required")

    from gateway.sticker_cache import (
        get_cached_description,
        cache_sticker_description,
        STICKER_VISION_PROMPT,
    )
    from gateway.sticker_library import add_sticker

    try:
        bot = _build_bot()
    except RuntimeError as e:
        return _err(str(e))

    from telegram.error import BadRequest
    try:
        sticker_set = await bot.get_sticker_set(set_name)
    except BadRequest as e:
        return _err(f"Telegram couldn't find sticker set {set_name!r}: {e}")
    except Exception as e:
        return _err(f"Failed to fetch sticker set: {e}")

    added = 0
    skipped = 0
    skipped_reasons = []

    for sticker in sticker_set.stickers:
        # Skip non-static formats: vision can't describe them.
        if sticker.is_animated or sticker.is_video:
            skipped += 1
            skipped_reasons.append(f"{sticker.file_unique_id} (animated/video)")
            continue

        cached = get_cached_description(sticker.file_unique_id)
        if cached and cached.get("description"):
            description = cached["description"]
            # If the legacy entry has no file_id, write the freshly-known one.
            if not cached.get("file_id"):
                cache_sticker_description(
                    sticker.file_unique_id, description,
                    cached.get("emoji", sticker.emoji or ""),
                    cached.get("set_name", sticker.set_name or ""),
                    file_id=sticker.file_id,
                )
        else:
            # Cache miss: download + vision, then write cache only if vision succeeded.
            # Matches _handle_sticker's behavior — never cache fallback descriptions
            # (would poison future inbound encounters with the same sticker).
            vision_succeeded = False
            try:
                file_obj = await sticker.get_file()
                image_bytes = await file_obj.download_as_bytearray()
                cached_path = cache_image_from_bytes(bytes(image_bytes), ext=".webp")
                from tools.vision_tools import vision_analyze_tool
                result_json = await vision_analyze_tool(
                    image_url=cached_path,
                    user_prompt=STICKER_VISION_PROMPT,
                )
                vresult = json.loads(result_json)
                if vresult.get("success"):
                    description = vresult.get("analysis", "a sticker")
                    vision_succeeded = True
                else:
                    description = f"a sticker with emoji {sticker.emoji}" if sticker.emoji else "a sticker"
            except Exception as e:
                logger.warning("[Sticker] vision failed for %s: %s", sticker.file_unique_id, e)
                description = f"a sticker with emoji {sticker.emoji}" if sticker.emoji else "a sticker"

            if vision_succeeded:
                cache_sticker_description(
                    sticker.file_unique_id, description,
                    emoji=sticker.emoji or "", set_name=sticker.set_name or "",
                    file_id=sticker.file_id,
                )

        add_sticker(sticker.file_unique_id, sticker.file_id, description, usage_notes="")
        added += 1

    return _ok({
        "set_name": set_name,
        "added": added,
        "skipped": skipped,
        "skipped_details": skipped_reasons,
    })


registry.register(
    name="add_set_to_library",
    toolset="stickers",
    schema=ADD_SET_SCHEMA,
    handler=add_set_to_library_handler,
    is_async=True,
    emoji="📦",
)
