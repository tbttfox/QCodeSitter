"""
Tests for the CommentToggle behavior.

Tests comment/uncomment toggling for single lines, selections,
multi-cursor, and edge cases.
"""

from __future__ import annotations

from QCodeSitter.behaviors.comment_toggle import CommentToggle
from QCodeSitter.cursors.state import CursorState
from tests.helpers import (
    set_cursor_position,
    set_cursor_selection,
)


class TestSingleLineComment:
    def test_comment_single_line(self, editor):
        editor.setPlainText("x = 1")
        set_cursor_position(editor, 2)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "# x = 1"

    def test_uncomment_single_line(self, editor):
        editor.setPlainText("# x = 1")
        set_cursor_position(editor, 3)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1"

    def test_comment_indented_line(self, editor):
        """The comment goes after the indent"""
        editor.setPlainText("    x = 1")
        set_cursor_position(editor, 6)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    # x = 1"

    def test_uncomment_indented_line(self, editor):
        editor.setPlainText("    # x = 1")
        set_cursor_position(editor, 6)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    x = 1"

    def test_comment_empty_line(self, editor):
        editor.setPlainText("")
        set_cursor_position(editor, 0)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == ""

    def test_comment_whitespace_only_line(self, editor):
        editor.setPlainText("    ")
        set_cursor_position(editor, 2)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "    "


class TestMultiLineComment:
    def test_comment_selected_lines(self, editor):
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        set_cursor_selection(editor, 0, 11)  # Select first two lines
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "# x = 1\n# y = 2\nz = 3"

    def test_uncomment_selected_lines(self, editor):
        editor.setPlainText("# x = 1\n# y = 2\nz = 3")
        set_cursor_selection(editor, 0, 15)  # Select first two lines
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1\ny = 2\nz = 3"

    def test_mixed_lines_get_commented(self, editor):
        editor.setPlainText("# x = 1\ny = 2\nz = 3")
        set_cursor_selection(editor, 0, 18)  # Select all lines
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# # x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"

    def test_comment_respects_min_indent(self, editor):
        """The comments line up at the smallest indent of the selected lines"""
        editor.setPlainText("    x = 1\n        y = 2\n    z = 3")
        set_cursor_selection(editor, 0, 31)  # Select all
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "    # x = 1"
        assert lines[1] == "    #     y = 2"  # Extra indent preserved after comment
        assert lines[2] == "    # z = 3"

    def test_comment_skips_empty_lines(self, editor):
        editor.setPlainText("x = 1\n\ny = 2")
        set_cursor_selection(editor, 0, 12)  # Select all
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == ""
        assert lines[2] == "# y = 2"

    def test_uncomment_with_empty_lines(self, editor):
        editor.setPlainText("# x = 1\n\n# y = 2")
        set_cursor_selection(editor, 0, 16)  # Select all
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "x = 1"
        assert lines[1] == ""
        assert lines[2] == "y = 2"


class TestMultiCursorComment:
    def test_multicursor_comment(self, editor):
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        set_cursor_position(editor, 2)  # On first line
        editor.cursors.secondary = [
            CursorState(8, 8),  # On second line
            CursorState(14, 14),  # On third line
        ]
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"

    def test_multicursor_uncomment(self, editor):
        editor.setPlainText("# x = 1\n# y = 2\n# z = 3")
        set_cursor_position(editor, 3)  # On first line
        editor.cursors.secondary = [
            CursorState(11, 11),  # On second line
            CursorState(19, 19),  # On third line
        ]
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "x = 1"
        assert lines[1] == "y = 2"
        assert lines[2] == "z = 3"

    def test_multicursor_with_selection(self, editor):
        """One cursor has a selection, and the other doesn't"""
        editor.setPlainText("x = 1\ny = 2\nz = 3")
        # Primary cursor selects first two lines
        set_cursor_selection(editor, 0, 11)
        # Secondary cursor on third line (no selection)
        editor.cursors.secondary = [
            CursorState(14, 14),
        ]
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "# x = 1"
        assert lines[1] == "# y = 2"
        assert lines[2] == "# z = 3"

    def test_cursors_sharing_a_line_toggle_it_once(self, editor):
        editor.setPlainText("x = 1\ny = 2")
        set_cursor_position(editor, 0)
        editor.cursors.secondary = [CursorState(1, 1), CursorState(6, 6)]
        editor.get_behavior(CommentToggle).toggle_comment()
        assert editor.toPlainText() == "# x = 1\n# y = 2"
        # The cursors on the first line merged, selecting it
        assert editor.cursors.primary() == CursorState(0, 7)
        assert editor.cursors.secondary == [CursorState(8, 15)]

    def test_selection_and_cursor_sharing_lines(self, editor):
        editor.setPlainText("a\nb\nc\nd")
        set_cursor_selection(editor, 0, 3)  # "a" and "b"
        editor.cursors.secondary = [CursorState(2, 2), CursorState(6, 6)]
        editor.get_behavior(CommentToggle).toggle_comment()
        assert editor.toPlainText() == "# a\n# b\nc\n# d"


class TestCommentToggleEdgeCases:
    def test_toggle_roundtrip(self, editor):
        original = "def foo():\n    return 1"
        editor.setPlainText(original)
        set_cursor_selection(editor, 0, len(original))
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        behavior.toggle_comment()
        assert editor.toPlainText() == original

    def test_comment_preserves_other_lines(self, editor):
        editor.setPlainText("a = 1\nb = 2\nc = 3")
        set_cursor_selection(editor, 6, 11)  # Select only "b = 2"
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        text = editor.toPlainText()
        lines = text.split("\n")
        assert lines[0] == "a = 1"
        assert lines[1] == "# b = 2"
        assert lines[2] == "c = 3"

    def test_uncomment_no_trailing_space(self, editor):
        editor.setPlainText("#x = 1")
        set_cursor_position(editor, 2)
        behavior = editor.get_behavior(CommentToggle)
        behavior.toggle_comment()
        assert editor.toPlainText() == "x = 1"

    def test_behavior_exists(self, editor):
        assert editor.get_behavior(CommentToggle) is not None
