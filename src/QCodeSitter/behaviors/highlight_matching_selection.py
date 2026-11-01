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
        self._set_colors({})
        self.editor.selectionChanged.connect(self.highlight_occurrences)
        self.watch_options({"colors": self._set_colors})
        self.apply_all_options()

    def _set_colors(self, colors: GuiColors) -> None:
        self._match_hl = gui_color(colors, "match_hl")

    def remove(self) -> None:
        super().remove()
        self.editor.selectionChanged.disconnect(self.highlight_occurrences)
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

            while True:
                search_cursor = doc.find(selected_text, search_cursor)
                if search_cursor.isNull():
                    break

                # Qt already highlights the selection itself
                if (
                    search_cursor.position() != cursor.position()
                    or search_cursor.anchor() != cursor.anchor()
                ):
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    selection.cursor = search_cursor
                    selection.format = fmt
                    extra_selections.append(selection)

        self.editor.set_selections(self.SOURCE, extra_selections)
