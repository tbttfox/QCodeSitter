from __future__ import annotations

from typing import TYPE_CHECKING

from ..cursors.state import CursorState, primary_first
from ..tracked_document import len16
from ..utils import MM, add_menu_action, make_shortcut_action
from . import Behavior

if TYPE_CHECKING:
    from Qt import QtCore, QtGui, QtWidgets

MOVE_UP = ("Move Lines Up", "Ctrl+Shift+Up")
MOVE_DOWN = ("Move Lines Down", "Ctrl+Shift+Down")
DUPLICATE = ("Duplicate", "Ctrl+Shift+D")


class LineCommands(Behavior):
    """Move the lines under the cursors up or down, and duplicate the selection
    or the current line, like PrEditor's QScintilla keys
    """

    def _commands(self):
        return (
            (*MOVE_UP, lambda: self.move_lines(up=True)),
            (*MOVE_DOWN, lambda: self.move_lines(up=False)),
            (*DUPLICATE, self.duplicate),
        )

    def get_hotkeys(self) -> list[QtGui.QAction]:
        return [
            make_shortcut_action(self.editor, shortcut, slot, label)
            for label, shortcut, slot in self._commands()
        ]

    def add_menu_actions(
        self, menu: QtWidgets.QMenu, pos: QtCore.QPoint | None
    ) -> None:
        for label, shortcut, slot in self._commands():
            add_menu_action(menu, label, slot, shortcut)

    def duplicate(self) -> None:
        """Copy each selection after itself and select the copy, or copy the
        line of a cursor without a selection below it
        """
        with self.editor.edit_session():
            for cursor in self.editor.citer.iterate_cursors(complete_all=True):
                if cursor.hasSelection():
                    text = cursor.selection().toPlainText()
                    end = cursor.selectionEnd()
                    cursor.setPosition(end)
                    cursor.insertText(text)
                    cursor.setPosition(end)
                    cursor.setPosition(end + len16(text), MM.KeepAnchor)
                else:
                    block = cursor.block()
                    column = cursor.positionInBlock()
                    cursor.setPosition(block.position() + len16(block.text()))
                    cursor.insertText("\n" + block.text())
                    cursor.setPosition(block.next().position() + column)

    def move_lines(self, up: bool) -> None:
        """Swap the lines under the cursors with the line above or below them

        Nothing moves if any of the lines is already at the edge of the document
        """
        doc = self.editor.document()
        states, primary_index = self.editor.cursors.in_document_order()

        # Group the cursors whose lines touch, as (first line, last line, states)
        groups: list[tuple[int, int, list[CursorState]]] = []
        for state in states:
            first = doc.findBlock(state.selectionStart()).blockNumber()
            end_block = doc.findBlock(state.selectionEnd())
            last = end_block.blockNumber()
            # A selection ending at the start of a line doesn't take that line
            if last > first and state.selectionEnd() == end_block.position():
                last -= 1
            if groups and first <= groups[-1][1] + 1:
                groups[-1] = (groups[-1][0], max(groups[-1][1], last), groups[-1][2])
                groups[-1][2].append(state)
            else:
                groups.append((first, last, [state]))

        if up and groups[0][0] == 0:
            return
        if not up and groups[-1][1] == doc.blockCount() - 1:
            return

        moved: list[CursorState] = []
        with self.editor.edit_session():
            cursor = self.editor.textCursor()
            cursor.beginEditBlock()
            try:
                for first, last, group in groups:
                    span_first, span_last = (
                        (first - 1, last) if up else (first, last + 1)
                    )
                    start_block = doc.findBlockByNumber(span_first)
                    end_block = doc.findBlockByNumber(span_last)
                    cursor.setPosition(start_block.position())
                    cursor.setPosition(
                        end_block.position() + len16(end_block.text()), MM.KeepAnchor
                    )
                    lines = cursor.selection().toPlainText().split("\n")
                    # The swapped line's length plus its newline is how far the others move
                    if up:
                        lines.append(lines.pop(0))
                        shift = -len16(lines[-1]) - 1
                    else:
                        lines.insert(0, lines.pop())
                        shift = len16(lines[0]) + 1
                    # The text keeps its length, so the later groups stay put
                    cursor.insertText("\n".join(lines))
                    moved += [
                        CursorState(s.anchor + shift, s.position + shift) for s in group
                    ]
            finally:
                cursor.endEditBlock()
            self.editor.cursors.replace_all(primary_first(moved, primary_index))
