from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from Qt import QtCore, QtGui

from ..tracked_document import len16, utf16_to_index
from ..utils import MM, MO, leading_whitespace
from .state import CursorState, primary_first

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


def _merge_overlapping(cursors: list[CursorState]) -> list[CursorState]:
    """Merge cursors that overlap, keeping the first cursor first

    Cursors that only touch merge when at least one of them has no selection,
    so two selections side by side stay separate

    A merged selection covers both selections, and is backward if either was
    """
    if len(cursors) <= 1:
        return cursors

    first = cursors[0]
    merged: list[CursorState] = []
    primary_index = 0
    for cursor in sorted(cursors, key=lambda c: c.selectionStart()):
        last = merged[-1] if merged else None
        if last is not None and (
            cursor.selectionStart() < last.selectionEnd()
            or (
                cursor.selectionStart() == last.selectionEnd()
                and not (cursor.hasSelection() and last.hasSelection())
            )
        ):
            start = last.selectionStart()
            end = max(last.selectionEnd(), cursor.selectionEnd())
            if last.is_backward() or cursor.is_backward():
                merged[-1] = CursorState(end, start)
            else:
                merged[-1] = CursorState(start, end)
        else:
            merged.append(cursor)
        if cursor is first:
            primary_index = len(merged) - 1
    return primary_first(merged, primary_index)


def _smart_home(qt_cursor: QtGui.QTextCursor, mode: MM) -> None:
    """Move to the first non-whitespace character, or column 0 if already there"""
    block = qt_cursor.block()
    line_start = block.position()
    text = block.text()
    # Whitespace is never a surrogate pair, so its length is its UTF-16 length
    indent_end = line_start + len(leading_whitespace(text))

    target = line_start if qt_cursor.position() == indent_end else indent_end
    qt_cursor.setPosition(target, mode)


class MultiCursor(QtCore.QObject):
    """The editor's cursors, and the commands that add and move them

    Qt only knows about the primary cursor. The others are kept here as
    CursorStates, and drawn by the MultiCursorPaint behavior. The commands that
    add cursors return whether they added one.
    """

    changed = QtCore.Signal()

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.editor = editor
        self.secondary: list[CursorState] = []

    def primary(self) -> CursorState:
        """Snapshot Qt's primary cursor as a CursorState"""
        return CursorState.from_cursor(self.editor.textCursor())

    def set_primary(self, state: CursorState) -> None:
        self.editor.setTextCursor(state.apply(self.editor.textCursor()))

    def in_document_order(self) -> tuple[list[CursorState], int]:
        """Get every cursor sorted by position, and the index of the primary one"""
        primary = self.primary()
        ret = sorted([primary, *self.secondary], key=lambda c: c.selectionStart())
        return ret, ret.index(primary)

    def _primary_first(self) -> list[CursorState]:
        return primary_first(*self.in_document_order())

    def replace_all(self, cursors: list[CursorState]) -> None:
        """Replace every cursor, merging any that overlap

        The first cursor becomes the primary, the rest become secondaries.
        """
        if not cursors:
            self.clear_secondary()
            return
        merged = _merge_overlapping(cursors)
        self.set_primary(merged[0])
        self.secondary = merged[1:]
        self.changed.emit()

    def clear_secondary(self) -> None:
        """Leave multi-cursor mode, keeping only the primary cursor"""
        self.secondary.clear()
        self.changed.emit()

    def add_next_occurrence(self) -> bool:
        """Add a cursor selecting the next occurrence of the primary selection

        With no selection, select the word under the cursor first.
        Returns whether a cursor was added
        """
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.WordUnderCursor)
            if not cursor.hasSelection():
                return False
            self.editor.setTextCursor(cursor)

        search_text = cursor.selectedText()
        all_cursors = self._primary_first()
        next_pos = self._find(search_text, max(c.selectionEnd() for c in all_cursors))
        if next_pos < 0:
            # Wrap around to the start, but only up to the first cursor
            next_pos = self._find(search_text, 0)
            if next_pos < 0 or next_pos >= min(c.selectionStart() for c in all_cursors):
                return False
        end = next_pos + len16(search_text)
        added = self._add([*all_cursors, CursorState(next_pos, end)])
        if added:
            self._scroll_to(end)
        return added

    def _scroll_to(self, position: int) -> None:
        """Scroll to show a position, leaving the primary cursor where it is"""
        # Qt only scrolls to the primary cursor, so borrow it to find the scroll
        editor = self.editor
        primary = editor.textCursor()
        bars = (editor.horizontalScrollBar(), editor.verticalScrollBar())
        editor.setTextCursor(
            CursorState(position, position).build_cursor(editor.document())
        )
        values = [bar.value() for bar in bars]
        editor.setTextCursor(primary)
        for bar, value in zip(bars, values):
            bar.setValue(value)

    def _find(self, search_text: str, start_pos: int) -> int:
        """Find the position of search_text after start_pos, or -1 if there is none

        QTextDocument.find only matches within one block, so search the raw
        text instead. Like selectedText, it separates blocks with U+2029, so
        multi-line selections match too
        """
        text = self.editor.document().toRawText()
        found = text.find(search_text, utf16_to_index(text, start_pos))
        return -1 if found < 0 else len16(text[:found])

    def move(self, operation: MO, select: bool = False) -> None:
        """Move every cursor, like QTextCursor.movePosition

        Args:
            operation: Where to move each cursor to
            select: Extend the selections, like holding Shift
        """
        mode = MM.KeepAnchor if select else MM.MoveAnchor
        self._move_each(lambda qt_cursor: qt_cursor.movePosition(operation, mode))

    def smart_home(self, select: bool = False) -> None:
        """Move every cursor to its line's indent, or to column 0 if it's there"""
        mode = MM.KeepAnchor if select else MM.MoveAnchor
        self._move_each(lambda qt_cursor: _smart_home(qt_cursor, mode))

    def _move_each(self, move: Callable[[QtGui.QTextCursor], object]) -> None:
        qt_cursor = QtGui.QTextCursor(self.editor.document())
        moved = []
        for state in self._primary_first():
            state.apply(qt_cursor)
            move(qt_cursor)
            moved.append(CursorState.from_cursor(qt_cursor))
        self.replace_all(moved)

    def selected_texts(self) -> list[str]:
        """Get the selected text of every cursor, in document order"""
        all_cursors, _primary_index = self.in_document_order()
        qt_cursor = QtGui.QTextCursor(self.editor.document())
        return [
            state.apply(qt_cursor).selectedText().replace(" ", "\n")
            for state in all_cursors
        ]

    def _add_adjacent(self, above: bool) -> bool:
        """Move the primary cursor up or down a line, leaving a cursor behind"""
        current_position = self.primary().position
        block = self.editor.document().findBlock(current_position)
        adj_block = block.previous() if above else block.next()
        if not block.isValid() or not adj_block.isValid():
            return False

        col = min(current_position - block.position(), len16(adj_block.text()))
        new_primary_pos = adj_block.position() + col
        return self._add(
            [
                CursorState(new_primary_pos, new_primary_pos),
                *self.secondary,
                CursorState(current_position, current_position),
            ]
        )

    def add_above(self) -> bool:
        """Move the primary cursor up a line, leaving a cursor behind"""
        return self._add_adjacent(True)

    def add_below(self) -> bool:
        """Move the primary cursor down a line, leaving a cursor behind"""
        return self._add_adjacent(False)

    def add_to_line_ends(self) -> bool:
        """Replace the selection with a cursor at the end of each of its lines

        Returns whether there are more cursors than before
        """
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return False

        doc = self.editor.document()
        block = doc.findBlock(cursor.selectionStart())
        end_block = doc.findBlock(cursor.selectionEnd())
        cursors = []
        while block.isValid():
            line_end = block.position() + len16(block.text())
            cursors.append(CursorState(line_end, line_end))
            if block == end_block:
                break
            block = block.next()
        return self._add(cursors)

    def add_at(self, position: int) -> bool:
        """Add a cursor at a position, like Alt+Click"""
        return self._add([*self._primary_first(), CursorState(position, position)])

    def _add(self, cursors: list[CursorState]) -> bool:
        """Replace every cursor, and return whether there are more than before

        A new cursor that overlaps another one merges into it, as does one
        that touches another when either of them has no selection
        """
        count = len(self.secondary)
        self.replace_all(cursors)
        return len(self.secondary) > count
