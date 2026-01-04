"""Unified cursor interface for single and multi-cursor operations.

This module provides a single access point for cursor operations that automatically
handles both single-cursor and multi-cursor modes transparently.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Any
from dataclasses import dataclass

if TYPE_CHECKING:
    from .line_editor import CodeEditor
    from Qt.QtGui import QTextCursor


@dataclass
class CursorOperation:
    """Represents a cursor operation that can be applied to single or multiple cursors.

    This class encapsulates the logic for performing an operation on cursors,
    with separate implementations for single-cursor and multi-cursor modes.
    """

    single_cursor_func: Callable[[QTextCursor], Any]
    """Function to execute for single-cursor mode. Takes a QTextCursor and returns the result."""

    multi_cursor_func: Callable[[], Any] | None = None
    """Optional function for multi-cursor mode. If None, uses the multi-cursor manager's built-in operations."""


class CursorInterface:
    """Unified interface for cursor operations.

    This class provides a single access point for all cursor-related operations,
    automatically dispatching to the appropriate single-cursor or multi-cursor
    implementation based on the current mode.

    Usage:
        # In a behavior's keyPressEvent:
        def keyPressEvent(self, event, hotkey):
            if self.editor.cursor.is_multi_mode:
                # Decide what to do in multi-cursor mode
                return self.editor.cursor.execute_multi(...)
            else:
                # Single cursor operation
                cursor = self.editor.cursor.get()
                ...
    """

    def __init__(self, editor: CodeEditor):
        self.editor = editor

    @property
    def is_multi_mode(self) -> bool:
        """Returns True if multi-cursor mode is currently active."""
        return self.editor.multi_cursor_manager.is_active()

    def get(self) -> QTextCursor:
        """Get the current primary cursor.

        This works in both single and multi-cursor modes - in multi-cursor mode,
        it returns the primary cursor from the multi-cursor manager.

        Returns:
            The primary QTextCursor
        """
        return self.editor.textCursor()

    def insert_text(self, text: str) -> None:
        """Insert text at current cursor(s).

        This is a convenience method that handles text insertion in both modes.

        Args:
            text: The text to insert
        """
        if self.is_multi_mode:
            self.editor.multi_cursor_manager.insert_text(text)
        else:
            cursor = self.get()
            cursor.insertText(text)
            self.editor.setTextCursor(cursor)

    def has_selection(self) -> bool:
        """Check if any cursor has a selection.

        In single-cursor mode, checks if the cursor has a selection.
        In multi-cursor mode, checks if ANY cursor has a selection.

        Returns:
            True if any cursor has a selection
        """
        if self.is_multi_mode:
            all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()
            return any(c.has_selection for c in all_cursors)
        else:
            return self.get().hasSelection()

    def get_selected_text(self) -> str | list[str]:
        """Get selected text from cursor(s).

        In single-cursor mode, returns a single string.
        In multi-cursor mode, returns a list of strings (one per cursor).

        Returns:
            String or list of strings depending on mode
        """
        if self.is_multi_mode:
            all_cursors, _primary_index = self.editor.multi_cursor_manager.get_all_cursors()
            return [
                self.editor.multi_cursor_manager._get_text(
                    c.selection_start, c.selection_end
                )
                for c in all_cursors
            ]
        else:
            return self.get().selectedText()
