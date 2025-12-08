from __future__ import annotations
from . import Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtWidgets

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class HighlightMatchingSelection(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.editor.selectionChanged.connect(self.highlight_occurrences)
        self.updateAll()

    def highlight_occurrences(self):
        """Highlight all occurrences of the currently selected text"""
        extra_selections = []

        # Get current selection
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        # Only highlight if there's a selection and it's not too long
        # Also require at least 2 characters to avoid highlighting single chars
        if selected_text and len(selected_text) >= 2 and len(selected_text) <= 100:
            # Create format for highlighting occurrences
            format = QtGui.QTextCharFormat()
            format.setBackground(
                QtGui.QColor(255, 255, 0, 80)
            )  # Light yellow with transparency

            # Find all occurrences
            doc = self.editor.document()
            search_cursor = QtGui.QTextCursor(doc)

            while True:
                search_cursor = doc.find(selected_text, search_cursor)
                if search_cursor.isNull():
                    break

                # Don't highlight the current selection itself
                if (
                    search_cursor.position() != cursor.position()
                    or search_cursor.anchor() != cursor.anchor()
                ):
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = format
                    extra_selections.append(selection)

        self.editor.setExtraSelections(extra_selections)
