from __future__ import annotations

from dataclasses import dataclass

from Qt import QtGui

from ..utils import MM


@dataclass
class CursorState:
    """A cursor's anchor and position in UTF-16 code units

    The selection methods mirror QTextCursor's names, so code can take either
    """

    anchor: int
    position: int

    @classmethod
    def from_cursor(cls, cursor: QtGui.QTextCursor) -> CursorState:
        return cls(cursor.anchor(), cursor.position())

    def hasSelection(self) -> bool:
        return self.anchor != self.position

    def is_backward(self) -> bool:
        """Whether the selection was made from right to left"""
        return self.anchor > self.position

    def selectionStart(self) -> int:
        return min(self.anchor, self.position)

    def selectionEnd(self) -> int:
        return max(self.anchor, self.position)

    def apply(self, cursor: QtGui.QTextCursor) -> QtGui.QTextCursor:
        """Move a QTextCursor to this state"""
        cursor.setPosition(self.anchor)
        cursor.setPosition(self.position, MM.KeepAnchor)
        return cursor

    def copy_from(self, cursor: QtGui.QTextCursor) -> None:
        self.anchor = cursor.anchor()
        self.position = cursor.position()

    def offset(self, offset: int) -> None:
        """Shift this state by a number of code units"""
        self.anchor += offset
        self.position += offset

    def build_cursor(self, document: QtGui.QTextDocument) -> QtGui.QTextCursor:
        return self.apply(QtGui.QTextCursor(document))


def primary_first(states: list[CursorState], primary_index: int) -> list[CursorState]:
    """Copy the states, moving the primary cursor's state to the front"""
    states = states[:]
    states.insert(0, states.pop(primary_index))
    return states
