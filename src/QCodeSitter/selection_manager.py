from __future__ import annotations
from typing import TYPE_CHECKING
from Qt.QtWidgets import QTextEdit

if TYPE_CHECKING:
    from .line_editor import CodeEditor


class SelectionManager:
    """Manages extra selections from multiple behaviors

    This allows multiple behaviors to contribute highlighting without overwriting each other.
    """

    def __init__(self, editor: CodeEditor):
        self.editor = editor
        self._selections: dict[str, list[QTextEdit.ExtraSelection]] = {}

    def set_selections(self, source: str, selections: list[QTextEdit.ExtraSelection]):
        """Set selections for a specific source (behavior)

        Args:
            source: Identifier for the source behavior (e.g., "bracket_matching", "selection_highlight")
            selections: List of extra selections to apply
        """
        self._selections[source] = selections
        self._update_editor()

    def clear_selections(self, source: str):
        """Clear selections for a specific source

        Args:
            source: Identifier for the source behavior
        """
        if source in self._selections:
            del self._selections[source]
            self._update_editor()

    def _update_editor(self):
        """Merge all selections and update the editor"""
        merged = []
        # Merge selections from all sources
        # Order matters - later sources will appear on top
        for source in sorted(self._selections.keys()):
            merged.extend(self._selections[source])

        self.editor.setExtraSelections(merged)
