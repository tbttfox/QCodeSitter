"""Tests for the multi-cursor line and span edits"""

from __future__ import annotations

import pytest
from Qt import QtGui

from QCodeSitter.cursors.line_edits import (
    edit_joined_spans,
    expand_to_lines,
    replace_lines,
    replace_lines_at_cursors,
)
from QCodeSitter.cursors.state import CursorState
from QCodeSitter.tracked_document import TrackedDocument
from tests.helpers import assert_tree_matches_fresh_parse


@pytest.fixture
def doc_cursor(qapp):
    """Makes a cursor in a new document, which lives until the test ends"""
    docs = []

    def make(text: str, anchor: int, position: int) -> QtGui.QTextCursor:
        doc = TrackedDocument()
        docs.append(doc)
        doc.setPlainText(text)
        cursor = QtGui.QTextCursor(doc)
        cursor.setPosition(anchor)
        cursor.setPosition(position, QtGui.QTextCursor.MoveMode.KeepAnchor)
        return cursor

    return make


def selections(editor) -> list[tuple[int, int]]:
    cursors, _ = editor.cursors.in_document_order()
    return [(c.anchor, c.position) for c in cursors]


def upper(lines: list[str]) -> list[str]:
    return [line.upper() for line in lines]


class TestExpandToLines:
    def test_no_selection_selects_the_line(self, doc_cursor):
        cursor = doc_cursor("ab\ncd\nef", 4, 4)
        expand_to_lines(cursor)
        assert cursor.selectedText() == "cd"

    def test_partial_lines_become_whole(self, doc_cursor):
        cursor = doc_cursor("ab\ncd\nef", 1, 4)
        expand_to_lines(cursor)
        assert cursor.selection().toPlainText() == "ab\ncd"


class TestReplaceLines:
    def test_replaces_and_selects_the_new_lines(self, doc_cursor):
        cursor = doc_cursor("ab\ncd\nef", 4, 4)
        replace_lines(cursor, lambda lines: ["x", "y"])
        assert cursor.document().toPlainText() == "ab\nx\ny\nef"
        assert (cursor.selectionStart(), cursor.selectionEnd()) == (3, 6)

    def test_selection_end_counts_utf16(self, doc_cursor):
        # The emoji is 2 UTF-16 code units
        cursor = doc_cursor("ab", 0, 0)
        replace_lines(cursor, lambda lines: ["😀"])
        assert cursor.selectionEnd() == 2


class TestReplaceLinesAtCursors:
    def test_each_line_is_replaced_once(self, editor):
        editor.setPlainText("ab\ncd\nef")
        # Two cursors on line 0, one on line 2
        editor.cursors.replace_all(
            [CursorState(0, 0), CursorState(1, 1), CursorState(7, 7)]
        )
        replace_lines_at_cursors(editor.citer, upper)
        assert editor.toPlainText() == "AB\ncd\nEF"
        # The two cursors on line 0 merged
        assert selections(editor) == [(0, 2), (6, 8)]
        assert_tree_matches_fresh_parse(editor)

    def test_later_joins_follow_earlier_edits(self, editor):
        editor.setPlainText("a\nb\nc")
        editor.cursors.replace_all([CursorState(0, 0), CursorState(4, 4)])
        # Each line becomes two, which moves the second join down a line
        replace_lines_at_cursors(editor.citer, lambda lines: [*lines, "-"])
        assert editor.toPlainText() == "a\n-\nb\nc\n-"
        assert selections(editor) == [(0, 3), (6, 9)]

    def test_selection_spanning_lines_joins_with_a_cursor_inside(self, editor):
        editor.setPlainText("ab\ncd\nef")
        editor.cursors.replace_all([CursorState(0, 4), CursorState(5, 5)])
        replace_lines_at_cursors(editor.citer, upper)
        assert editor.toPlainText() == "AB\nCD\nef"
        assert selections(editor) == [(0, 5)]


class TestEditJoinedSpans:
    def test_touching_spans_join_and_shift_is_reported(self, editor):
        editor.setPlainText("aaaa bbbb cccc")
        editor.cursors.replace_all(
            [CursorState(0, 2), CursorState(2, 4), CursorState(10, 12)]
        )
        calls = []

        def span_of(cursor):
            return cursor.selectionStart(), cursor.selectionEnd()

        def edit_join(cursor, span, shift):
            calls.append((span, shift))
            # The span is from before any edits, so move it by the shift
            cursor.setPosition(span[0] + shift)
            cursor.setPosition(span[1] + shift, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText("X")

        edit_joined_spans(editor.citer, span_of, edit_join)
        # The first two spans touch, so they are one edit
        assert [span for span, _shift in calls] == [(0, 4), (10, 12)]
        # The first edit shrank the text by 3, which moved the last cursor
        assert [shift for _span, shift in calls] == [0, -3]
        assert editor.toPlainText() == "X bbbb Xcc"
        assert_tree_matches_fresh_parse(editor)
