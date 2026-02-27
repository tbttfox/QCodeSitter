"""
pytest configuration and fixtures for QCodeSitter integration tests.

This module provides fixtures for creating CodeEditor instances with various
configurations for testing different features like multi-cursor editing,
syntax highlighting, behaviors, and more.
"""

from __future__ import annotations

import pytest
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt import QtGui

from QCodeSitter.code_editor import CodeEditor, CursorState
from QCodeSitter.editor_options import EditorOptions
from QCodeSitter.hl_groups import DARK_THEME, read_theme
from QCodeSitter.highlight_query import HIGHLIGHT_QUERY

# Import behaviors
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.overscroll import Overscroll
from QCodeSitter.behaviors.highlight_matching_selection import (
    HighlightMatchingSelection,
)
from QCodeSitter.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.auto_bracket import AutoBracket
from QCodeSitter.behaviors.tab_completion import TabCompletion
from QCodeSitter.behaviors.providers.identifiers import IdentifierProvider
from QCodeSitter.behaviors.code_folding import CodeFolding
from QCodeSitter.behaviors.multi_cursor_paint import MultiCursorPaint
from QCodeSitter.behaviors.comment_toggle import CommentToggle


@pytest.fixture(scope="session")
def python_language():
    """Provide the Python tree-sitter language for the session."""
    return Language(tspython.language())


@pytest.fixture
def default_options(python_language):
    """Create default editor options for testing."""

    col, syn = read_theme(DARK_THEME)
    return EditorOptions(
        {
            "space_indent_width": 4,
            "tab_indent_width": 8,
            "indent_using_tabs": False,
            "language_name": "python",
            "language": python_language,
            "highlights": (HIGHLIGHT_QUERY, syn),
            "colors": col,
            "font": QtGui.QFont("Monospace", pointSize=10),
            "vim_completion_keys": False,
            "debounce_delay": 0,  # No debounce for tests
            "auto_bracket_enabled": True,
            "auto_bracket_pairs": "()[]{}\"\"''``",
            "indent_bracket_pairs": ["()", "[]", "{}"],
            "highlight_bracket_pairs": ["()", "[]", "{}"],
            "highlight_quote_pairs": "\"'`",
        }
    )


@pytest.fixture
def minimal_options(python_language):
    """Create minimal editor options (no behaviors)."""
    col, _syn = read_theme(DARK_THEME)
    return EditorOptions(
        {
            "space_indent_width": 4,
            "tab_indent_width": 4,
            "indent_using_tabs": False,
            "language": python_language,
            "colors": col,
            "font": QtGui.QFont("Monospace", pointSize=10),
        }
    )


@pytest.fixture
def editor(qtbot, default_options):
    """Create a CodeEditor instance with default options and all behaviors."""
    editor = CodeEditor(default_options)
    qtbot.addWidget(editor)

    # Add all standard behaviors
    _, tab_completion = editor.addBehavior(TabCompletion)
    tab_completion.addProvider(IdentifierProvider)

    editor.addBehavior(SyntaxHighlighting)
    editor.addBehavior(SmartIndent)
    editor.addBehavior(HighlightMatchingBrackets)
    editor.addBehavior(HighlightMatchingSelection)
    editor.addBehavior(LineNumber)
    editor.addBehavior(Overscroll)
    editor.addBehavior(MultiCursorPaint)
    editor.addBehavior(AutoBracket)
    editor.addBehavior(CodeFolding)
    editor.addBehavior(CommentToggle)

    editor.show()
    qtbot.waitExposed(editor)
    return editor


@pytest.fixture
def bare_editor(qtbot, minimal_options):
    """Create a bare CodeEditor instance without behaviors."""
    editor = CodeEditor(minimal_options)
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    return editor


@pytest.fixture
def editor_with_text(editor):
    """Create an editor pre-filled with sample Python code."""
    sample_code = '''def hello(name):
    """Say hello to someone."""
    if name:
        print(f"Hello, {name}!")
    else:
        print("Hello, World!")

class Greeter:
    def __init__(self, greeting="Hello"):
        self.greeting = greeting

    def greet(self, name):
        return f"{self.greeting}, {name}!"
'''
    editor.setPlainText(sample_code)
    # Move cursor to start
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    return editor


@pytest.fixture
def editor_with_multicursor(editor):
    """Create an editor with multiple cursors set up."""
    editor.setPlainText("foo\nfoo\nfoo\nbar\nbar")
    # Position primary cursor at start
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    # Add secondary cursors at start of lines 2 and 3
    editor.secondary_cursors = [
        CursorState(4, 4),  # Start of line 2
        CursorState(8, 8),  # Start of line 3
    ]
    return editor
