from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from Qt.QtCore import Signal, Qt
from Qt.QtGui import QKeySequence, QFont
from Qt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFrame,
    QMessageBox,
)

from .key_sequence_recorder import KeySequenceRecorderDialog

if TYPE_CHECKING:
    from ..shortcut_manager import ShortcutSlot


# Conflict warning styling
CONFLICT_FRAME_STYLE = (
    "QFrame { background-color: #fff3cd; border: 1px solid #ffc107; padding: 8px; }"
    "QLabel { color: #856404; }"  # Dark brown text for good contrast
)


class ShortcutDetailsPanel(QWidget):
    """Panel showing detailed information for a selected shortcut slot.

    Displays:
        - Slot name and description
        - List of assigned shortcuts (with Edit/Delete buttons)
        - Add shortcut button
        - Reset to defaults button
        - Conflict warnings (if any)
    """

    shortcutsChanged = Signal(str, object)  # (group_name, slot)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_slot: Optional[ShortcutSlot] = None
        self._current_group_name: Optional[str] = None

        self._setup_ui()
        self._set_empty_state()

    def _setup_ui(self):
        """Build the details panel UI."""
        layout = QVBoxLayout(self)

        # Slot name label (bold, larger font)
        self._name_label = QLabel()
        font = QFont()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self._name_label.setFont(font)
        layout.addWidget(self._name_label)

        # Description label
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self._desc_label)

        layout.addSpacing(10)

        # "Assigned Shortcuts:" label
        shortcuts_label = QLabel("Assigned Shortcuts:")
        layout.addWidget(shortcuts_label)

        # List of shortcuts
        self._shortcut_list = QListWidget()
        self._shortcut_list.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self._shortcut_list, stretch=1)

        # Action buttons
        button_layout = QHBoxLayout()

        self._add_button = QPushButton("Add Shortcut")
        self._add_button.clicked.connect(self._on_add_shortcut)
        button_layout.addWidget(self._add_button)

        self._reset_button = QPushButton("Reset to Defaults")
        self._reset_button.clicked.connect(self._on_reset_to_defaults)
        button_layout.addWidget(self._reset_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Conflict warning frame (hidden by default)
        self._conflict_frame = QFrame()
        self._conflict_frame.setFrameStyle(QFrame.StyledPanel)
        self._conflict_frame.setStyleSheet(CONFLICT_FRAME_STYLE)
        conflict_layout = QVBoxLayout(self._conflict_frame)
        conflict_layout.setContentsMargins(8, 8, 8, 8)

        self._conflict_label = QLabel()
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setTextFormat(Qt.RichText)
        conflict_layout.addWidget(self._conflict_label)

        self._conflict_frame.hide()
        layout.addWidget(self._conflict_frame)

    def set_slot(self, group_name: str, slot: ShortcutSlot):
        """Set the slot to display details for.

        Args:
            group_name: The name of the group containing the slot
            slot: The ShortcutSlot to display
        """
        self._current_slot = slot
        self._current_group_name = group_name

        # Update labels
        self._name_label.setText(slot.name)
        self._desc_label.setText(slot.desc)

        # Update shortcut list
        self._refresh_shortcut_list()

        # Enable buttons
        self._add_button.setEnabled(True)
        self._reset_button.setEnabled(True)

        # Hide conflict warning (will be shown if conflicts exist)
        self._conflict_frame.hide()

    def _set_empty_state(self):
        """Set panel to empty state (no slot selected)."""
        self._name_label.setText("No shortcut selected")
        self._desc_label.setText("Select a shortcut from the tree to view details.")
        self._shortcut_list.clear()
        self._add_button.setEnabled(False)
        self._reset_button.setEnabled(False)
        self._conflict_frame.hide()

    def _refresh_shortcut_list(self):
        """Refresh the list of assigned shortcuts."""
        self._shortcut_list.clear()

        if not self._current_slot:
            return

        for keyseq in self._current_slot.assigned:
            self._add_shortcut_item(keyseq)

    def _add_shortcut_item(self, keyseq: QKeySequence):
        """Add a shortcut item to the list.

        Args:
            keyseq: The key sequence to add
        """
        item = QListWidgetItem()
        item.setData(Qt.UserRole, keyseq)

        # Create widget for this item
        widget = ShortcutItemWidget(keyseq)
        widget.editRequested.connect(self._on_edit_shortcut)
        widget.deleteRequested.connect(self._on_delete_shortcut)

        self._shortcut_list.addItem(item)
        self._shortcut_list.setItemWidget(item, widget)
        item.setSizeHint(widget.sizeHint())

    def _on_add_shortcut(self):
        """Handle Add Shortcut button click."""
        if not self._current_slot:
            return

        # Show recorder dialog
        keyseq = KeySequenceRecorderDialog.record_sequence(self)

        if keyseq and not keyseq.isEmpty():
            # Add to slot's assigned shortcuts
            self._current_slot.assigned.append(keyseq)

            # Refresh display
            self._refresh_shortcut_list()

            # Notify parent
            self._emit_shortcuts_changed()

    def _on_edit_shortcut(self, old_keyseq: QKeySequence):
        """Handle Edit button click for a shortcut.

        Args:
            old_keyseq: The existing key sequence being edited
        """
        if not self._current_slot:
            return

        # Show recorder dialog with existing sequence
        new_keyseq = KeySequenceRecorderDialog.record_sequence(self, old_keyseq)

        if new_keyseq and not new_keyseq.isEmpty():
            # Replace old sequence with new one
            try:
                idx = self._current_slot.assigned.index(old_keyseq)
                self._current_slot.assigned[idx] = new_keyseq

                # Refresh display
                self._refresh_shortcut_list()

                # Notify parent
                self._emit_shortcuts_changed()
            except ValueError:
                # Old sequence not found - shouldn't happen
                pass

    def _on_delete_shortcut(self, keyseq: QKeySequence):
        """Handle Delete button click for a shortcut.

        Args:
            keyseq: The key sequence to delete
        """
        if not self._current_slot:
            return

        # Confirm deletion
        result = QMessageBox.question(
            self,
            "Delete Shortcut",
            f"Remove shortcut '{keyseq.toString(QKeySequence.NativeText)}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result == QMessageBox.Yes:
            try:
                self._current_slot.assigned.remove(keyseq)

                # Refresh display
                self._refresh_shortcut_list()

                # Notify parent
                self._emit_shortcuts_changed()
            except ValueError:
                # Sequence not found - shouldn't happen
                pass

    def _on_reset_to_defaults(self):
        """Handle Reset to Defaults button click."""
        if not self._current_slot:
            return

        # Confirm reset
        result = QMessageBox.question(
            self,
            "Reset to Defaults",
            f"Reset '{self._current_slot.name}' to default shortcuts?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result == QMessageBox.Yes:
            # Copy defaults to assigned (deep copy to avoid reference issues)
            self._current_slot.assigned = [
                QKeySequence(seq.toString(QKeySequence.PortableText))
                for seq in self._current_slot.defaults
            ]

            # Refresh display
            self._refresh_shortcut_list()

            # Notify parent
            self._emit_shortcuts_changed()

    def _emit_shortcuts_changed(self):
        """Emit signal that shortcuts have changed."""
        if self._current_slot and self._current_group_name:
            self.shortcutsChanged.emit(self._current_group_name, self._current_slot)

    def show_conflicts(self, conflicts: list[tuple[str, str]]):
        """Show conflict warning for the current slot.

        Args:
            conflicts: List of (group_name, slot_name) tuples that have conflicts
        """
        if not conflicts:
            self._conflict_frame.hide()
            return

        conflict_text = "<b>\u26A0 Conflicts detected:</b><br>"
        conflict_text += "<ul>"
        for group, slot in conflicts:
            conflict_text += f"<li>{group} &gt; {slot}</li>"
        conflict_text += "</ul>"

        self._conflict_label.setText(conflict_text)
        self._conflict_frame.show()

    def clear_conflicts(self):
        """Clear conflict warning display."""
        self._conflict_frame.hide()


class ShortcutItemWidget(QWidget):
    """Widget for displaying a single shortcut in the list.

    Layout: [Key Sequence Text    ] [Edit] [Delete]
    """

    editRequested = Signal(QKeySequence)
    deleteRequested = Signal(QKeySequence)

    def __init__(self, keysequence: QKeySequence, parent=None):
        super().__init__(parent)
        self._keysequence = keysequence
        self._setup_ui()

    def _setup_ui(self):
        """Build the widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # Key sequence display
        label = QLabel(self._keysequence.toString(QKeySequence.NativeText))
        label.setMinimumWidth(200)
        layout.addWidget(label, stretch=1)

        # Edit button
        edit_button = QPushButton("Edit")
        edit_button.setMaximumWidth(60)
        edit_button.clicked.connect(lambda: self.editRequested.emit(self._keysequence))
        layout.addWidget(edit_button)

        # Delete button
        delete_button = QPushButton("Delete")
        delete_button.setMaximumWidth(60)
        delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(self._keysequence)
        )
        layout.addWidget(delete_button)
