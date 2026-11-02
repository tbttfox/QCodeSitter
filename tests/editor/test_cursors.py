"""Tests for the cursor model: merging, the iterator, and the controller"""

from __future__ import annotations

from Qt import QtCore, QtGui

from QCodeSitter.cursors.iterator import CursorIterator
from QCodeSitter.cursors.multi import MultiCursor
from QCodeSitter.cursors.state import CursorState
from tests.helpers import (
    get_cursor_positions,
    set_cursor_position,
    simulate_keypress,
)


class TestCursorMerging:
    def test_merge_adjacent_cursors(self, editor):
        editor.setPlainText("Hello World")
        editor.cursors.replace_all([CursorState(5, 5), CursorState(5, 5)])
        # Should merge into one cursor
        cursors, _ = editor.cursors.in_document_order()
        assert len(cursors) == 1

    def test_merge_overlapping_selections(self, editor):
        editor.setPlainText("Hello World")
        # "Hello " and "o World" overlap
        editor.cursors.replace_all([CursorState(0, 6), CursorState(4, 11)])
        # Should merge into one selection covering the whole text
        cursors, _ = editor.cursors.in_document_order()
        assert cursors == [CursorState(0, 11)]

    def test_merge_keeps_backward_selections_backward(self, editor):
        editor.setPlainText("Hello World")
        editor.cursors.replace_all([CursorState(6, 0), CursorState(11, 4)])
        assert editor.cursors.in_document_order()[0] == [CursorState(11, 0)]

    def test_merge_backward_selection_with_a_cursor_inside(self, editor):
        editor.setPlainText("Hello World")
        editor.cursors.replace_all([CursorState(8, 2), CursorState(5, 5)])
        assert editor.cursors.in_document_order()[0] == [CursorState(8, 2)]

    def test_touching_selections_stay_separate(self, editor):
        editor.setPlainText("Hello World")
        editor.cursors.replace_all([CursorState(0, 2), CursorState(2, 4)])
        assert editor.cursors.in_document_order()[0] == [
            CursorState(0, 2),
            CursorState(2, 4),
        ]

    def test_cursor_touching_a_selection_merges(self, editor):
        editor.setPlainText("Hello World")
        editor.cursors.replace_all([CursorState(0, 2), CursorState(2, 2)])
        assert editor.cursors.in_document_order()[0] == [CursorState(0, 2)]


class TestCursorIterator:
    def test_cursor_iterator_offset_tracking(self, editor):
        editor.setPlainText("abc\nabc\nabc")
        set_cursor_position(editor, 0)
        editor.cursors.secondary = [CursorState(4, 4), CursorState(8, 8)]
        # Insert "X" at each position - later cursors should be offset
        simulate_keypress(editor, QtCore.Qt.Key.Key_X, "X")
        text = editor.toPlainText()
        lines = text.split("\n")
        # Each line should start with "X"
        assert all(line.startswith("X") for line in lines)

    def test_cursor_iterator_with_deletions(self, editor):
        editor.setPlainText("Xabc\nXabc\nXabc")
        set_cursor_position(editor, 0)
        editor.cursors.secondary = [CursorState(5, 5), CursorState(10, 10)]
        # Delete first char at each position
        simulate_keypress(editor, QtCore.Qt.Key.Key_Delete)
        text = editor.toPlainText()
        lines = text.split("\n")
        # "X" should be removed from each line
        assert all(line == "abc" for line in lines)


class TestCursorIteratorPasses:
    """CursorIterator, which editor.citer is, used directly"""

    def test_completed_cursors_are_skipped_for_the_session(self, editor):
        editor.setPlainText("a\nb\nc")
        editor.cursors.replace_all(
            [CursorState(0, 0), CursorState(2, 2), CursorState(4, 4)]
        )
        citer: CursorIterator = editor.citer
        with editor.edit_session():
            for cursor in citer.iterate_cursors():
                if cursor.block().text() == "b":
                    cursor.insertText("1")
                    citer.mark_cursor_completed()
            assert not citer.all_completed()
            for cursor in citer.iterate_cursors(complete_all=True):
                cursor.insertText("2")
            assert citer.all_completed()
        assert editor.toPlainText() == "2a\n1b\n2c"

    def test_read_cursors_leaves_the_cursors(self, editor):
        editor.setPlainText("abc def")
        editor.cursors.replace_all([CursorState(1, 1), CursorState(5, 5)])
        changes = []
        editor.cursors.changed.connect(lambda: changes.append(1))
        positions = []
        for cursor in editor.citer.read_cursors():
            positions.append(cursor.position())
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        assert positions == [1, 5]
        assert get_cursor_positions(editor) == [1, 5]
        assert changes == []

    def test_replacing_the_cursors_ends_the_pass(self, editor):
        editor.setPlainText("a\nb\nc")
        editor.cursors.replace_all(
            [CursorState(1, 1), CursorState(3, 3), CursorState(5, 5)]
        )
        citer = editor.citer
        with editor.edit_session():
            for cursor in citer.iterate_cursors():
                cursor.insertText("!")
                citer.mark_cursor_completed()
                editor.cursors.replace_all([CursorState(0, 0)])
            # The new cursor starts out not completed
            assert not citer.all_completed()
        assert editor.toPlainText() == "a!\nb\nc"
        assert get_cursor_positions(editor) == [0]

    def test_a_pass_is_one_undo_step(self, editor):
        editor.setPlainText("a\nb")
        editor.cursors.replace_all([CursorState(1, 1), CursorState(3, 3)])
        editor.insert_text("!")
        assert editor.toPlainText() == "a!\nb!"
        editor.document().undo()
        assert editor.toPlainText() == "a\nb"


class TestMultiCursorController:
    def test_controller_owns_cursors(self, editor):
        cursors: MultiCursor = editor.cursors
        editor.setPlainText("abc abc abc")
        changes = []
        cursors.changed.connect(lambda: changes.append(1))
        cursors.replace_all([CursorState(4, 4), CursorState(0, 0)])
        assert cursors.primary() == CursorState(4, 4)
        assert cursors.secondary == [CursorState(0, 0)]
        assert cursors.in_document_order() == (
            [CursorState(0, 0), CursorState(4, 4)],
            1,
        )
        cursors.clear_secondary()
        assert cursors.secondary == []
        assert changes == [1, 1]

    def test_move_keeps_the_primary(self, editor):
        editor.setPlainText("abc\nabc")
        editor.cursors.replace_all([CursorState(5, 5), CursorState(1, 1)])
        editor.cursors.move(QtGui.QTextCursor.MoveOperation.Right)
        assert editor.cursors.primary() == CursorState(6, 6)

    def test_add_next_occurrence_wraps(self, editor):
        editor.setPlainText("foo bar foo")
        editor.cursors.replace_all([CursorState(8, 11)])
        assert editor.cursors.add_next_occurrence()
        assert editor.cursors.secondary == [CursorState(0, 3)]
        assert not editor.cursors.add_next_occurrence()

    def test_add_commands_say_whether_they_added(self, editor):
        cursors: MultiCursor = editor.cursors
        editor.setPlainText("ab\ncd")
        cursors.replace_all([CursorState(0, 0)])
        assert not cursors.add_above()
        assert cursors.add_below()
        assert not cursors.add_at(0)
        assert cursors.add_at(1)
        cursors.replace_all([CursorState(0, 0)])
        assert not cursors.add_to_line_ends()
        cursors.replace_all([CursorState(0, 1)])
        assert not cursors.add_to_line_ends()
        assert get_cursor_positions(editor) == [2]
        cursors.replace_all([CursorState(0, 5)])
        assert cursors.add_to_line_ends()
        assert get_cursor_positions(editor) == [2, 5]

    def test_add_next_occurrence_with_no_other_match(self, editor):
        editor.setPlainText("foo bar")
        editor.cursors.replace_all([CursorState(0, 3)])
        assert not editor.cursors.add_next_occurrence()
        assert editor.cursors.secondary == []

    def test_replacing_cursors_mid_session_starts_over(self, editor):
        """Cursors replaced inside an edit session are the ones the next pass edits"""
        editor.setPlainText("abc\nabc")
        with editor.edit_session():
            editor.cursors.replace_all([CursorState(1, 1), CursorState(5, 5)])
            editor.insert_text("X")
        assert editor.toPlainText() == "aXbc\naXbc"
