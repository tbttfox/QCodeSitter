from __future__ import annotations

from Qt.QtCore import Signal
from Qt.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel


class SearchFilterWidget(QWidget):
    """Search bar widget for filtering shortcuts.

    Provides a search field that emits filterChanged signal when text changes.
    """

    filterChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Build the search widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search icon label
        search_label = QLabel("Search:")
        layout.addWidget(search_label)

        # Search input field
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(
            "Filter by name, description, or shortcut..."
        )
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_edit)

    def _on_text_changed(self, text: str):
        """Handle search text changes.

        Args:
            text: The new search text
        """
        self.filterChanged.emit(text)

    def clear(self):
        """Clear the search field."""
        self._search_edit.clear()

    def set_focus(self):
        """Set focus to the search field."""
        self._search_edit.setFocus()
