"""Multi-cursor edits that join the cursors sharing a line or a span"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from Qt import QtGui

from ..tracked_document import len16
from ..utils import MM, MO

if TYPE_CHECKING:
    from .iterator import CursorIterator


def expand_to_lines(cursor: QtGui.QTextCursor) -> None:
    """Expand a cursor selection to whole lines
    If there is no selection, expand to the current line
    """
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    cursor.setPosition(start)
    cursor.movePosition(MO.StartOfLine)
    cursor.setPosition(end, MM.KeepAnchor)
    cursor.movePosition(MO.EndOfLine, MM.KeepAnchor)


def replace_lines(
    cursor: QtGui.QTextCursor, transform: Callable[[list[str]], list[str]]
) -> None:
    """Replace the whole lines under the cursor, and select the new lines

    Args:
        cursor: The cursor whose selection (or current line) to replace
        transform: Takes the lines, without their newlines, and returns new ones
    """
    expand_to_lines(cursor)
    start = cursor.selectionStart()
    lines = cursor.selection().toPlainText().split("\n")
    new_text = "\n".join(transform(lines))
    cursor.insertText(new_text)
    cursor.setPosition(start)
    cursor.setPosition(start + len16(new_text), MM.KeepAnchor)


def edit_joined_spans(
    citer: CursorIterator,
    span_of: Callable[[QtGui.QTextCursor], tuple[int, int]],
    edit_join: Callable[[QtGui.QTextCursor, tuple[int, int], int], None],
) -> None:
    """Edit the spans of every cursor, once for each group of spans that overlap or touch

    The first cursor of each join makes the edit, and the other cursors in the
    join take its selection afterwards, so the cursors merge

    Args:
        citer: The editor's cursor iterator
        span_of: Gives the (start, end) span to edit for a cursor. It may move
            the cursor
        edit_join: Edits a joined span at the first cursor of the join. The int
            is how far the edits at the joins before it have moved this cursor
    """
    starts = []
    spans = []
    for cursor in citer.read_cursors():
        starts.append(cursor.selectionStart())
        spans.append(span_of(cursor))

    # A span can start before the span of the cursor before it, but then it
    # overlaps it, so the joins are still in the order of the cursors
    joined: list[tuple[int, int]] = []
    joins = [0] * len(spans)
    for i in sorted(range(len(spans)), key=lambda i: spans[i][0]):
        start, end = spans[i]
        if joined and start <= joined[-1][1]:
            joined[-1] = (joined[-1][0], max(joined[-1][1], end))
        else:
            joined.append((start, end))
        joins[i] = len(joined) - 1

    # The iterator goes first, so it runs to its end and writes the cursors back
    edited_join = -1
    edited = (0, 0)
    for (i, cursor), join in zip(
        enumerate(citer.iterate_cursors(complete_all=True)), joins
    ):
        if join != edited_join:
            edit_join(cursor, joined[join], cursor.selectionStart() - starts[i])
            edited_join = join
            edited = (cursor.anchor(), cursor.position())
        else:
            cursor.setPosition(edited[0])
            cursor.setPosition(edited[1], MM.KeepAnchor)


def replace_lines_at_cursors(
    citer: CursorIterator, transform: Callable[[list[str]], list[str]]
) -> None:
    """Replace the whole lines under every cursor, and select the new lines

    Cursors that share a line are joined, so each line is replaced once. Each
    cursor in a join selects all of its new lines, so the cursors merge

    Args:
        citer: The editor's cursor iterator
        transform: Takes the lines, without their newlines, and returns new ones
    """

    def line_span(cursor: QtGui.QTextCursor) -> tuple[int, int]:
        document = cursor.document()
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
        return first, last

    def replace_join(cursor: QtGui.QTextCursor, span: tuple[int, int], _: int) -> None:
        # The first cursor of a join is on its first line, wherever the
        # edits at the joins before it have moved that line to
        first, last = span
        start_block = cursor.document().findBlock(cursor.selectionStart())
        end_block = cursor.document().findBlockByNumber(
            start_block.blockNumber() + last - first
        )
        cursor.setPosition(start_block.position())
        cursor.setPosition(end_block.position(), MM.KeepAnchor)
        replace_lines(cursor, transform)

    edit_joined_spans(citer, line_span, replace_join)
