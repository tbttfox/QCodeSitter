from __future__ import annotations

from collections.abc import Callable

from Qt import QtCore, QtGui, QtWidgets

from .constants import ENC

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


def len16(val: str) -> int:
    """Get the number of UTF-16 code units, where surrogate pairs count as 2"""
    return len(val.encode(ENC)) // 2


def utf16_to_index(text: str, col: int) -> int:
    """Convert a UTF-16 column in text (ie: positionInBlock) to a str index

    A column inside a surrogate pair rounds down to the start of the pair
    """
    return len(text.encode(ENC)[: col * 2].decode(ENC, errors="ignore"))


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
