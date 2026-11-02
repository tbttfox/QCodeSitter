"""
pytest configuration and fixtures for QCodeSitter integration tests.

This module provides fixtures for creating CodeEditor instances with various
configurations for testing different features like multi-cursor editing,
syntax highlighting, behaviors, and more.
"""

from __future__ import annotations

import pytest
import tree_sitter_python as tspython
from Qt import QtGui, QtWidgets
from tree_sitter import Language

from QCodeSitter import CodeEditor, EditorOptions, defaults
from QCodeSitter.cursors.state import CursorState
from QCodeSitter.highlighting.themes import DARK_THEME, read_theme


@pytest.fixture(scope="session")
def python_language():
    """Provide the Python tree-sitter language for the session."""
    return Language(tspython.language())


def make_test_options(python_language: Language) -> EditorOptions:
    """The default options, with a fixed font and no completion delay"""
    options = defaults.default_options(
        DARK_THEME, python_language, QtGui.QFont("Monospace", pointSize=10)
    )
    options.update({"vim_completion_keys": False, "debounce_delay": 0})
    return options


@pytest.fixture
def clipboard(qapp):
    """The app clipboard, emptied for the test and put back afterwards

    Every test shares the one clipboard, so tests that use it start from nothing
    """
    board = QtWidgets.QApplication.clipboard()
    saved = board.text()
    board.clear()
    yield board
    board.setText(saved)


def install_test_behaviors(editor: CodeEditor):
    """Every built-in behavior, including the ones that are off by default"""
    defaults.install_default_behaviors(editor, optional=True)


@pytest.fixture
def default_options(qapp, python_language):
    """Create default editor options for testing."""
    return make_test_options(python_language)


@pytest.fixture
def minimal_options(qapp, python_language):
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
    install_test_behaviors(editor)
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
    editor.cursors.replace_all(
        [CursorState(0, 0), CursorState(4, 4), CursorState(8, 8)]
    )
    return editor
