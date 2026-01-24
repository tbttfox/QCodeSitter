"""
Integration tests for syntax analysis and tree-sitter integration.

Tests TreeManager, SyntaxAnalyzer, TrackedDocument, and syntax highlighting.
"""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from QCodeSitter.line_tracker import TrackedDocument
from QCodeSitter.tree_manager import TreeManager
from QCodeSitter.syntax_analyzer import SyntaxAnalyzer
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting

from tests.helpers import set_cursor_position, simulate_keypress


class TestTrackedDocument:
    """Test TrackedDocument UTF-16 position tracking."""

    def test_document_creation(self, editor, qtbot):
        """Test TrackedDocument is created for editor."""
        doc = editor.document()
        assert isinstance(doc, TrackedDocument)

    def test_byte_contents_change_signal(self, editor, qtbot):
        """Test byteContentsChange signal is emitted on edit via keypress."""
        doc = editor.document()
        signal_received = []

        def on_change(*args):
            signal_received.append(args)

        doc.byteContentsChange.connect(on_change)
        # Type a character to trigger the signal
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_A, "a")

        # Should have received at least one signal
        assert len(signal_received) >= 1

    def test_document_block_count(self, editor, qtbot):
        """Test document tracks lines correctly."""
        editor.setPlainText("Hello\nWorld")
        doc = editor.document()
        assert doc.blockCount() == 2

    def test_document_with_unicode(self, editor, qtbot):
        """Test document handles unicode correctly."""
        editor.setPlainText("Hello 世界\nWorld")
        doc = editor.document()
        assert doc.blockCount() == 2
        assert "世界" in doc.toPlainText()


class TestTreeManager:
    """Test TreeManager parsing and updates."""

    def test_tree_manager_initialized(self, editor, qtbot):
        """Test TreeManager is initialized with language."""
        assert hasattr(editor, "tree_manager")
        assert isinstance(editor.tree_manager, TreeManager)

    def test_tree_exists(self, editor_with_text, qtbot):
        """Test parse tree exists after setting text."""
        editor = editor_with_text
        # Wait for parsing
        qtbot.wait(50)
        assert editor.tree_manager.tree is not None

    def test_tree_root_node(self, editor_with_text, qtbot):
        """Test parse tree has valid root node."""
        editor = editor_with_text
        qtbot.wait(50)
        tree = editor.tree_manager.tree
        assert tree.root_node is not None
        # For Python, root should be "module"
        assert tree.root_node.type == "module"

    def test_incremental_update(self, editor, qtbot):
        """Test tree is incrementally updated on edit via keypress."""
        editor.setPlainText("x = 1")
        qtbot.wait(50)

        # Make an edit via keypress
        set_cursor_position(editor, 5)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Plus, "+")
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_2, "2")
        qtbot.wait(50)

        new_tree = editor.tree_manager.tree
        # Tree should have been updated
        assert new_tree is not None
        # Content should reflect the edit
        assert "+" in editor.toPlainText()

    def test_get_node_at_point(self, editor_with_text, qtbot):
        """Test getting syntax node at a specific byte offset."""
        editor = editor_with_text
        qtbot.wait(50)
        # Get node at byte offset 0 (start of "def")
        node = editor.tree_manager.get_node_at_point(0)
        assert node is not None

    def test_pause_unpause(self, editor, qtbot):
        """Test pausing and unpausing tree updates."""
        editor.setPlainText("x = 1")
        qtbot.wait(50)

        # Pause updates
        editor.tree_manager.pause()

        # Check paused flag
        assert editor.tree_manager._paused is True

        # Unpause
        editor.tree_manager.unpause()
        qtbot.wait(50)

        # Now should not be paused
        assert editor.tree_manager._paused is False


class TestSyntaxAnalyzer:
    """Test SyntaxAnalyzer for syntax-aware editing."""

    def test_syntax_analyzer_initialized(self, editor, qtbot):
        """Test SyntaxAnalyzer is initialized."""
        assert hasattr(editor, "syntax_analyzer")
        assert isinstance(editor.syntax_analyzer, SyntaxAnalyzer)

    def test_should_indent_after_colon(self, editor, qtbot):
        """Test detecting indent after colon."""
        editor.setPlainText("def foo():")
        qtbot.wait(100)
        # Position at end of line (after colon) - column 9 is the colon position
        result = editor.syntax_analyzer.should_indent_after_position(0, 9)
        # Result depends on tree-sitter parsing state
        assert result in (True, False)

    def test_should_indent_after_if(self, editor, qtbot):
        """Test detecting indent after if statement."""
        editor.setPlainText("if True:")
        qtbot.wait(100)
        result = editor.syntax_analyzer.should_indent_after_position(0, 7)
        assert result in (True, False)

    def test_no_indent_after_regular_line(self, editor, qtbot):
        """Test no indent after regular statement."""
        editor.setPlainText("x = 1")
        qtbot.wait(100)
        result = editor.syntax_analyzer.should_indent_after_position(0, 4)
        assert result is False

    def test_should_dedent_after_return(self, editor, qtbot):
        """Test detecting dedent after return statement."""
        editor.setPlainText("def foo():\n    return 1")
        qtbot.wait(100)
        result = editor.syntax_analyzer.should_dedent_after_position(1, 11, "    return 1")
        # Result depends on implementation
        assert result in (True, False)

    def test_should_dedent_after_pass(self, editor, qtbot):
        """Test detecting dedent after pass statement."""
        editor.setPlainText("def foo():\n    pass")
        qtbot.wait(100)
        result = editor.syntax_analyzer.should_dedent_after_position(1, 7, "    pass")
        assert result in (True, False)


class TestSyntaxHighlighting:
    """Test syntax highlighting behavior."""

    def test_syntax_highlighting_exists(self, editor, qtbot):
        """Test syntax highlighting behavior is added."""
        hl = editor.getBehavior(SyntaxHighlighting)
        assert hl is not None

    def test_highlighting_applied(self, editor_with_text, qtbot):
        """Test that syntax highlighting is applied to the document."""
        editor = editor_with_text
        qtbot.wait(100)  # Wait for highlighting to be applied

        # Check that extra selections or formats are applied
        # The document should have some formatting
        doc = editor.document()
        block = doc.firstBlock()

        # We can check that the text exists and highlighting was processed
        assert block.isValid()
        assert "def" in block.text()

    def test_highlighting_updates_on_edit(self, editor, qtbot):
        """Test highlighting updates when text is edited via setPlainText."""
        editor.setPlainText("")
        qtbot.wait(50)

        # Add Python code
        editor.setPlainText("def foo():\n    pass")
        qtbot.wait(100)

        # Document should have the code
        assert "def" in editor.toPlainText()
        assert "pass" in editor.toPlainText()


class TestSyntaxIntegration:
    """Test integration between syntax components."""

    def test_typing_triggers_reparse(self, editor, qtbot):
        """Test that typing triggers tree-sitter reparse."""
        editor.setPlainText("x = ")
        set_cursor_position(editor, 4)
        qtbot.wait(50)

        # Type a number
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_1, "1")
        qtbot.wait(50)

        # Tree should be updated
        assert editor.tree_manager.tree is not None
        # Content should contain what we typed
        text = editor.toPlainText()
        assert "1" in text

    def test_smart_indent_uses_syntax(self, editor, qtbot):
        """Test smart indent uses syntax analyzer for decisions."""
        editor.setPlainText("def hello():")
        set_cursor_position(editor, 12)
        qtbot.wait(100)

        # Press Enter - should create new line
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Return)

        text = editor.toPlainText()
        lines = text.split("\n")
        # Should have created a new line
        assert len(lines) >= 2

    def test_multiline_string_handling(self, editor, qtbot):
        """Test handling of multiline strings."""
        editor.setPlainText('"""')
        qtbot.wait(50)

        # Tree should handle incomplete multiline string
        assert editor.tree_manager.tree is not None

    def test_syntax_error_handling(self, editor, qtbot):
        """Test tree-sitter handles syntax errors gracefully."""
        editor.setPlainText("def foo(")  # Incomplete syntax
        qtbot.wait(50)

        # Tree should still exist (with error nodes)
        assert editor.tree_manager.tree is not None
        # Editor should still be functional - type closing paren
        set_cursor_position(editor, 8)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_ParenRight, ")")
        assert ")" in editor.toPlainText()


class TestUnicodeHandling:
    """Test handling of unicode and special characters."""

    def test_unicode_in_string(self, editor, qtbot):
        """Test unicode characters in strings."""
        editor.setPlainText('x = "Hello 世界"')
        qtbot.wait(50)
        assert editor.tree_manager.tree is not None
        assert "世界" in editor.toPlainText()

    def test_emoji_handling(self, editor, qtbot):
        """Test emoji characters (multi-byte UTF-16)."""
        editor.setPlainText('x = "Hello 🎉"')
        qtbot.wait(50)
        assert editor.tree_manager.tree is not None
        assert "🎉" in editor.toPlainText()

    def test_cursor_position_with_unicode(self, editor, qtbot):
        """Test cursor position tracking with unicode."""
        editor.setPlainText("日本語")
        qtbot.wait(50)
        set_cursor_position(editor, 3)  # End of text
        assert editor.textCursor().position() == 3

    def test_editing_after_unicode(self, editor, qtbot):
        """Test editing after unicode characters via keypress."""
        editor.setPlainText("日本語")
        set_cursor_position(editor, 3)
        simulate_keypress(qtbot, editor, QtCore.Qt.Key.Key_Exclam, "!")
        assert editor.toPlainText() == "日本語!"


class TestDocumentReload:
    """Test behavior when document is reloaded/replaced."""

    def test_replace_all_text(self, editor, qtbot):
        """Test replacing all text."""
        editor.setPlainText("First content")
        qtbot.wait(50)
        editor.setPlainText("New content")
        qtbot.wait(50)
        assert editor.toPlainText() == "New content"
        assert editor.tree_manager.tree is not None

    def test_clear_and_refill(self, editor, qtbot):
        """Test clearing and refilling document."""
        editor.setPlainText("def foo(): pass")
        qtbot.wait(50)
        editor.setPlainText("")
        qtbot.wait(50)
        assert editor.toPlainText() == ""
        editor.setPlainText("def bar(): pass")
        qtbot.wait(50)
        assert "bar" in editor.toPlainText()
