"""
Agent-curated sticker library for Telegram outbound sending.

The library is the agent's visible workspace: stickers it has been told to
remember, with editable usage notes the user teaches over time. Distinct from
``sticker_cache.py`` (hidden infrastructure for inbound vision descriptions).

Schema (~/.hermes/sticker_library.json)::

    {
      "stickers": {
        "<file_unique_id>": {
          "file_id":      "...",   # bot-scoped capability token; required to send
          "description":  "...",   # initialized from cache; agent may edit
          "usage_notes":  "..."    # agent fills as it learns from the user
        }
      }
    }
"""

import json
from typing import Optional

from hermes_cli.config import get_hermes_home


LIBRARY_PATH = get_hermes_home() / "sticker_library.json"


def _load() -> dict:
    """Load the library from disk. Returns an empty library on missing/corrupt file."""
    if not LIBRARY_PATH.exists():
        return {"stickers": {}}
    try:
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "stickers" not in data:
            return {"stickers": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"stickers": {}}


def _save(data: dict) -> None:
    """Persist the library atomically-ish (parent dir created, full overwrite)."""
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def add_sticker(
    file_unique_id: str,
    file_id: str,
    description: str,
    usage_notes: str = "",
) -> None:
    """Add or replace a library entry. file_id and description are required."""
    data = _load()
    data["stickers"][file_unique_id] = {
        "file_id": file_id,
        "description": description,
        "usage_notes": usage_notes,
    }
    _save(data)


def get_sticker(file_unique_id: str) -> Optional[dict]:
    """Return the library entry for a sticker, or None if not present."""
    data = _load()
    return data["stickers"].get(file_unique_id)


def edit_sticker(
    file_unique_id: str,
    description: Optional[str] = None,
    usage_notes: Optional[str] = None,
) -> None:
    """
    Update fields on an existing entry. Only non-None fields are changed.
    Empty string is a valid value (it clears the field). file_id is immutable
    here — it's set at add-time and only refreshed by re-adding.

    Raises KeyError if the entry doesn't exist.
    """
    data = _load()
    if file_unique_id not in data["stickers"]:
        raise KeyError(file_unique_id)
    entry = data["stickers"][file_unique_id]
    if description is not None:
        entry["description"] = description
    if usage_notes is not None:
        entry["usage_notes"] = usage_notes
    _save(data)


def remove_sticker(file_unique_id: str) -> None:
    """Delete an entry. No-op if it doesn't exist."""
    data = _load()
    if data["stickers"].pop(file_unique_id, None) is not None:
        _save(data)


def list_stickers() -> list[dict]:
    """
    Return a list of agent-facing entries. Each dict has::

        {"file_unique_id": ..., "description": ..., "usage_notes": ...}

    file_id is intentionally omitted — agents reference stickers by
    file_unique_id and never need the bot-scoped file_id directly.
    """
    data = _load()
    return [
        {
            "file_unique_id": fuid,
            "description": entry["description"],
            "usage_notes": entry["usage_notes"],
        }
        for fuid, entry in data["stickers"].items()
    ]


def get_session_context_section() -> Optional[str]:
    """
    Build the ``## Sticker Library`` section to append to the session-context
    system-prompt block. Returns None when the library is empty (no section
    should be emitted in that case).

    Used by ``gateway.session.build_session_context_prompt`` for Telegram
    sessions only.
    """
    entries = list_stickers()
    if not entries:
        return None
    lines = [
        "## Sticker Library",
        "",
        "Each entry: file_unique_id | description | usage_notes",
    ]
    for entry in entries:
        notes = entry["usage_notes"] or "(no usage notes yet)"
        lines.append(f"- {entry['file_unique_id']} | {entry['description']} | {notes}")
    return "\n".join(lines)
