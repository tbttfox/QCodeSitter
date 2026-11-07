from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtGui, QtWidgets

from ..gui_colors import GuiColors, gui_color
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class HighlightMatchingSelection(Behavior):
    """Highlight the other occurrences of the selected text"""

    SOURCE = "selection_highlight"
    MIN_LENGTH = 2
    MAX_LENGTH = 100

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.watch_options({"colors": self._set_colors})
        self.connect(self.editor.selectionChanged, self.highlight_occurrences)
        # Ctrl+D adds cursors without changing the primary selection
        self.connect(self.editor.cursors.changed, self.highlight_occurrences)

    def _set_colors(self, colors: GuiColors) -> None:
        self._match_hl = gui_color(colors, "match_hl")

    def on_remove(self) -> None:
        self.editor.clear_selections(self.SOURCE)

    def highlight_occurrences(self) -> None:
        """Highlight all occurrences of the selected text"""
        extra_selections = []
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        # Single characters would match everywhere
        if self.MIN_LENGTH <= len(selected_text) <= self.MAX_LENGTH:
            fmt = QtGui.QTextCharFormat()
            fmt.setBackground(self._match_hl)
            doc = self.editor.document()
            search_cursor = QtGui.QTextCursor(doc)
            # Qt or MultiCursorPaint already draws the cursors' own selections, and
            # a highlight over them would hide which occurrences are selected
            selected = {
                (state.selectionStart(), state.selectionEnd())
                for state in (cursor, *self.editor.cursors.secondary)
            }
            case_sensitive = QtGui.QTextDocument.FindFlag.FindCaseSensitively

            while True:
                search_cursor = doc.find(selected_text, search_cursor, case_sensitive)
                if search_cursor.isNull():
                    break

                found = (search_cursor.selectionStart(), search_cursor.selectionEnd())
                if found not in selected:
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = fmt
                    extra_selections.append(selection)

        self.editor.set_selections(self.SOURCE, extra_selections)
