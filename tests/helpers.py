"""
Helper functions for QCodeSitter tests.
"""

from __future__ import annotations

from Qt import QtCore, QtGui
from tree_sitter import Language, Parser

from QCodeSitter import EditorOptions, defaults
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.code_editor import CodeEditor
from QCodeSitter.themes import DARK_THEME
from QCodeSitter.tracked_document import ENC


def make_test_options(python_language: Language) -> EditorOptions:
    """The default options, with a fixed font and no completion delay"""
    options = defaults.default_options(
        DARK_THEME, python_language, QtGui.QFont("Monospace", pointSize=10)
    )
    options.update({"vim_completion_keys": False, "debounce_delay": 0})
    return options


def install_test_behaviors(editor: CodeEditor):
    """Every built-in behavior, including the ones that are off by default"""
    defaults.install_default_behaviors(editor, optional=True)


def get_cursor_positions(editor: CodeEditor) -> list[int]:
    """Get all cursor positions (primary + secondary) sorted."""
    cursors, _ = editor.cursors.in_document_order()
    return [c.position for c in cursors]


def set_cursor_position(editor: CodeEditor, position: int):
    """Set the primary cursor position."""
    cursor = editor.textCursor()
    cursor.setPosition(position)
    editor.setTextCursor(cursor)


def set_cursor_selection(editor: CodeEditor, anchor: int, position: int):
    """Set the primary cursor with a selection."""
    cursor = editor.textCursor()
    cursor.setPosition(anchor)
    cursor.setPosition(position, QtGui.QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def simulate_keypress(
    editor: CodeEditor,
    key: QtCore.Qt.Key,
    text: str = "",
    modifiers: QtCore.Qt.KeyboardModifier = QtCore.Qt.KeyboardModifier.NoModifier,
):
    """Simulate a key press event on the editor."""
    event = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress,
        key,
        modifiers,
        text,
    )
    editor.keyPressEvent(event)


def simulate_text_input(editor: CodeEditor, text: str):
    """Simulate typing text into the editor."""
    for char in text:
        key = getattr(QtCore.Qt.Key, f"Key_{char.upper()}", QtCore.Qt.Key.Key_unknown)
        simulate_keypress(editor, key, char)


def fresh_tree_str(editor: CodeEditor) -> str:
    """Parse the document from scratch, to compare against the incremental tree"""
    parser = Parser(editor.tree_manager.language)
    return str(
        parser.parse(editor.toPlainText().encode(ENC), encoding="utf16").root_node
    )


def assert_tree_matches_fresh_parse(editor: CodeEditor):
    assert str(editor.tree_manager.root_node) == fresh_tree_str(editor)


def highlight_formats(editor: CodeEditor) -> list[list[tuple[int, int, str]]]:
    """Get the highlight formats for every block in the document"""
    out = []
    block = editor.document().firstBlock()
    while block.isValid():
        out.append(
            [
                (rng.start, rng.length, rng.format.foreground().color().name())
                for rng in block.layout().formats()
            ]
        )
        block = block.next()
    return out


def assert_matches_full_highlight(editor: CodeEditor):
    """The incremental highlighting matches highlighting the whole document again"""
    incremental = highlight_formats(editor)
    editor.get_behavior(SyntaxHighlighting).highlighter.rehighlight()
    assert incremental == highlight_formats(editor)
