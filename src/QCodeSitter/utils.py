"""Short names for the Qt enums, indentation string helpers, and Qt5/Qt6 event and
action shims
"""

from __future__ import annotations

from collections.abc import Callable

from Qt import QtCore, QtGui, QtWidgets

MO = QtGui.QTextCursor.MoveOperation
MM = QtGui.QTextCursor.MoveMode
KEY = QtCore.Qt.Key
MOD = QtCore.Qt.KeyboardModifier


def leading_whitespace(text: str) -> str:
    """The indentation at the start of a line"""
    return text[: len(text) - len(text.lstrip())]


def dedent_string(indent: str, indent_using_tabs: bool, space_indent_width: int) -> str:
    """Remove one level of indentation from the indent string"""
    if indent_using_tabs:
        return indent.removesuffix("\t")
    trailing_spaces = len(indent) - len(indent.rstrip(" "))
    remove = min(space_indent_width, trailing_spaces)
    return indent[:-remove] if remove else indent


def event_pos(event: QtGui.QMouseEvent | QtGui.QDropEvent) -> QtCore.QPoint:
    """The event position as a QPoint in both Qt5 and Qt6"""
    position = getattr(event, "position", None)
    return position().toPoint() if position is not None else event.pos()


def make_shortcut_action(
    parent: QtWidgets.QWidget,
    shortcut: str,
    slot: Callable[..., object],
    name: str = "",
) -> QtWidgets.QAction:
    """Create an action for a keyboard shortcut that only fires in the parent widget"""
    action = QtWidgets.QAction(name, parent)
    action.setShortcut(QtGui.QKeySequence(shortcut))
    action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
    action.triggered.connect(slot)
    return action
