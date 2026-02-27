"""
Tests for the CommentToggle behavior.

Tests comment/uncomment toggling for single lines, selections,
multi-cursor, and edge cases.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.code_editor import CursorState
from QCodeSitter.behaviors.comment_toggle import CommentToggle

from tests.helpers import (
    set_cursor_position,
    set_cursor_selection,
)


class TestSingleLineComment:
    """Test commenting/uncommenting a single line (no selection)."""

    def test_comment_single_line(self, editor, qtbot):
        """Test commenting a single uncommented line."""
        editor.setPlainText("x = 1")
        set_cursor_position(editor, 2)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "# x = 1"

    def test_uncomment_single_line(self, editor, qtbot):
        """Test uncommenting a single commented line."""
        editor.setPlainText("# x = 1")
        set_cursor_position(editor, 3)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1"

    def test_comment_indented_line(self, editor, qtbot):
        """Test commenting an indented line inserts comment after indent."""
        editor.setPlainText("    x = 1")
        set_cursor_position(editor, 6)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    # x = 1"

    def test_uncomment_indented_line(self, editor, qtbot):
        """Test uncommenting an indented commented line."""
        editor.setPlainText("    # x = 1")
        set_cursor_position(editor, 6)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    x = 1"

    def test_comment_empty_line(self, editor, qtbot):
        """Test toggling comment on an empty line does nothing."""
        editor.setPlainText("")
        set_cursor_position(editor, 0)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == ""

    def test_comment_whitespace_only_line(self, editor, qtbot):
        """Test toggling comment on whitespace-only line does nothing."""
        editor.setPlainText("    ")
        set_cursor_position(editor, 2)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    "


class TestMultiLineComment:
    """Test commenting/uncommenting with a selection spanning multiple lines."""

    def test_comment_selected_lines(self, editor, qtbot):
        """Test commenting multiple selected lines."""
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        set_cursor_selection(editor, 0, 11)  # Select first two lines
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "# x = 1\n# y = 2\nz = 3"

    def test_uncomment_selected_lines(self, editor, qtbot):
        """Test uncommenting multiple selected commented lines."""
        editor.setPlainText("# x = 1\n# y = 2\nz = 3")
        set_cursor_selection(editor, 0, 15)  # Select first two lines
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1\ny = 2\nz = 3"

    def test_mixed_lines_get_commented(self, editor, qtbot):
        """Test mixed commented/uncommented lines all get commented."""
        editor.setPlainText("# x = 1\ny = 2\nz = 3")
        set_cursor_selection(editor, 0, 18)  # Select all lines
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# # x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"

    def test_comment_respects_min_indent(self, editor, qtbot):
        """Test commenting respects minimum indentation of selected lines."""
        editor.setPlainText("    x = 1\n        y = 2\n    z = 3")
        set_cursor_selection(editor, 0, 31)  # Select all
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "    # x = 1"
        assert lines[1] == "    #     y = 2"  # Extra indent preserved after comment
        assert lines[2] == "    # z = 3"

    def test_comment_skips_empty_lines(self, editor, qtbot):
        """Test commenting skips empty lines in selection."""
        editor.setPlainText("x = 1\n\ny = 2")
        set_cursor_selection(editor, 0, 12)  # Select all
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == ""
        assert lines[2] == "# y = 2"

    def test_uncomment_with_empty_lines(self, editor, qtbot):
        """Test uncommenting with empty lines in between."""
        editor.setPlainText("# x = 1\n\n# y = 2")
        set_cursor_selection(editor, 0, 16)  # Select all
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "x = 1"
        assert lines[1] == ""
        assert lines[2] == "y = 2"


class TestMultiCursorComment:
    """Test comment toggle with multiple cursors."""

    def test_multicursor_comment(self, editor, qtbot):
        """Test commenting with multiple cursors on different lines."""
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        set_cursor_position(editor, 2)  # On first line
        editor.secondary_cursors = [
            CursorState(8, 8),  # On second line
            CursorState(14, 14),  # On third line
        ]
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"

    def test_multicursor_uncomment(self, editor, qtbot):
        """Test uncommenting with multiple cursors."""
        editor.setPlainText("# x = 1\n# y = 2\n# z = 3")
        set_cursor_position(editor, 3)  # On first line
        editor.secondary_cursors = [
            CursorState(11, 11),  # On second line
            CursorState(19, 19),  # On third line
        ]
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "x = 1"
        assert lines[1] == "y = 2"
        assert lines[2] == "z = 3"

    def test_multicursor_with_selection(self, editor, qtbot):
        """Test multi-cursor where one cursor has a selection."""
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        # Primary cursor selects first two lines
        set_cursor_selection(editor, 0, 11)
        # Secondary cursor on third line (no selection)
        editor.secondary_cursors = [
            CursorState(14, 14),
        ]
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"


class TestCommentToggleEdgeCases:
    """Test edge cases for comment toggling."""

    def test_toggle_roundtrip(self, editor, qtbot):
        """Test that comment then uncomment returns to original."""
        original = "def foo():\n    return 1"
        editor.setPlainText(original)
        set_cursor_selection(editor, 0, len(original))
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        behavior.toggle_comment()
        assert editor.toPlainText() == original

    def test_comment_preserves_other_lines(self, editor, qtbot):
        """Test that commenting doesn't affect lines outside selection."""
        editor.setPlainText("a = 1\nb = 2\nc = 3")
        set_cursor_selection(editor, 6, 11)  # Select only "b = 2"
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "a = 1"
        assert lines[1] == "# b = 2"
        assert lines[2] == "c = 3"

    def test_uncomment_no_trailing_space(self, editor, qtbot):
        """Test uncommenting a line where comment has no trailing space."""
        editor.setPlainText("#x = 1")
        set_cursor_position(editor, 2)
        behavior = editor.getBehavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1"

    def test_behavior_exists(self, editor, qtbot):
        """Test CommentToggle behavior is registered."""
        assert editor.getBehavior(CommentToggle) is not None
