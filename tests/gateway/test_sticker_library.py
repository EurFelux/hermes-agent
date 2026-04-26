"""Tests for gateway/sticker_library.py — agent-curated sticker library."""

import json
from unittest.mock import patch

import pytest


class TestLoadSave:
    def test_load_missing_file_returns_empty_library(self, tmp_path):
        path = tmp_path / "nope.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import _load
            assert _load() == {"stickers": {}}

    def test_load_corrupt_file_returns_empty_library(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json{{{")
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import _load
            assert _load() == {"stickers": {}}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "library.json"
        data = {"stickers": {"uid_1": {"file_id": "F1", "description": "A cat", "usage_notes": ""}}}
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import _save, _load
            _save(data)
            assert _load() == data


class TestCRUD:
    def test_add_sticker_creates_entry(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, get_sticker
            add_sticker(
                file_unique_id="uid_1",
                file_id="FILE_1",
                description="A cat",
                usage_notes="",
            )
            entry = get_sticker("uid_1")
        assert entry == {"file_id": "FILE_1", "description": "A cat", "usage_notes": ""}

    def test_add_sticker_overwrites_existing(self, tmp_path):
        """Re-adding the same file_unique_id replaces the entry (idempotent contract)."""
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, get_sticker
            add_sticker("uid_1", "F1", "old desc", "old notes")
            add_sticker("uid_1", "F2", "new desc", "")
            entry = get_sticker("uid_1")
        assert entry == {"file_id": "F2", "description": "new desc", "usage_notes": ""}

    def test_get_sticker_missing_returns_none(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import get_sticker
            assert get_sticker("nope") is None


class TestEdit:
    def test_edit_sticker_overwrites_named_fields_only(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, edit_sticker, get_sticker
            add_sticker("uid_1", "F1", "old desc", "old notes")
            edit_sticker("uid_1", description="new desc")  # usage_notes untouched
            entry = get_sticker("uid_1")
        assert entry["description"] == "new desc"
        assert entry["usage_notes"] == "old notes"
        assert entry["file_id"] == "F1"  # immutable

    def test_edit_sticker_can_set_usage_notes_to_empty_string(self, tmp_path):
        """Empty string is a real value — it clears notes; only None means 'no change'."""
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, edit_sticker, get_sticker
            add_sticker("uid_1", "F1", "desc", "old notes")
            edit_sticker("uid_1", usage_notes="")
            entry = get_sticker("uid_1")
        assert entry["usage_notes"] == ""

    def test_edit_sticker_missing_raises(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import edit_sticker
            with pytest.raises(KeyError):
                edit_sticker("nope", description="x")


class TestRemove:
    def test_remove_existing(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, remove_sticker, get_sticker
            add_sticker("uid_1", "F1", "desc")
            remove_sticker("uid_1")
            assert get_sticker("uid_1") is None

    def test_remove_missing_is_noop(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import remove_sticker
            remove_sticker("nope")  # should not raise


class TestList:
    def test_list_empty(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import list_stickers
            assert list_stickers() == []

    def test_list_returns_records_with_id(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, list_stickers
            add_sticker("uid_1", "F1", "A cat", "greetings")
            add_sticker("uid_2", "F2", "A panda", "")
            entries = list_stickers()
        ids = {e["file_unique_id"] for e in entries}
        assert ids == {"uid_1", "uid_2"}
        cat_entry = next(e for e in entries if e["file_unique_id"] == "uid_1")
        assert cat_entry["description"] == "A cat"
        assert cat_entry["usage_notes"] == "greetings"
        # file_id is internal — not exposed in agent-facing list
        assert "file_id" not in cat_entry


class TestSessionContextSection:
    def test_empty_library_returns_none(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import get_session_context_section
            assert get_session_context_section() is None

    def test_non_empty_library_includes_each_sticker(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, get_session_context_section
            add_sticker("uid_1", "F1", "A cat", "greetings")
            add_sticker("uid_2", "F2", "A panda", "")
            section = get_session_context_section()
        assert section is not None
        assert "## Sticker Library" in section
        # Behavioral assertion: every entry's id appears
        assert "uid_1" in section
        assert "uid_2" in section
        # And their descriptions
        assert "A cat" in section
        assert "A panda" in section

    def test_empty_usage_notes_rendered_with_marker(self, tmp_path):
        path = tmp_path / "library.json"
        with patch("gateway.sticker_library.LIBRARY_PATH", path):
            from gateway.sticker_library import add_sticker, get_session_context_section
            add_sticker("uid_1", "F1", "A cat", "")
            section = get_session_context_section()
        # The agent should be able to tell empty notes from real notes
        assert "(no usage notes yet)" in section
