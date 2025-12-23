from __future__ import annotations
from typing import Optional
from Qt import QtWidgets, QtCore, QtGui
from Qt.QtCore import Qt

from .hotkey_manager import HotkeyManager, HotkeyGroup, HotkeySlot, hk


class KeySequenceCapture(QtWidgets.QLineEdit):
    """Widget for capturing keyboard shortcuts"""

    keySequenceCaptured = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Press keys to capture...")
        self.setReadOnly(True)
        self._capturing = False

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Start capturing on click"""
        self._capturing = True
        self.setFocus()
        self.setText("")
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Capture key combination"""
        if not self._capturing:
            super().keyPressEvent(event)
            return

        # Ignore pure modifier keys
        key = event.key()
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        # Build hotkey string
        mods = event.modifiers()
        hotkey_str = hk(key, mods)

        self.setText(hotkey_str)
        self.keySequenceCaptured.emit(hotkey_str)
        self._capturing = False

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        """Stop capturing when focus is lost"""
        self._capturing = False
        super().focusOutEvent(event)


class HotkeyTreeWidget(QtWidgets.QTreeWidget):
    """Tree widget for displaying hotkey groups and slots"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Action", "Hotkeys", "Description"])
        self.setColumnWidth(0, 250)
        self.setColumnWidth(1, 200)
        self.setColumnWidth(2, 300)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        # Store references to slot items
        self._slot_items: dict[HotkeySlot, QtWidgets.QTreeWidgetItem] = {}

    def populate_from_manager(self, manager: HotkeyManager):
        """Populate tree from HotkeyManager"""
        self.clear()
        self._slot_items.clear()

        for group in manager.hotkey_groups:
            group_item = QtWidgets.QTreeWidgetItem(self, [group.name, "", ""])
            group_item.setExpanded(True)
            group_item.setFont(0, QtGui.QFont("", -1, QtGui.QFont.Weight.Bold))

            for slot in group.slots:
                # Format hotkeys
                hotkeys_str = ", ".join(slot.assigned) if slot.assigned else "(none)"

                # Create slot item
                slot_item = QtWidgets.QTreeWidgetItem(group_item, [
                    slot.name,
                    hotkeys_str,
                    slot.description or ""
                ])

                # Store reference
                self._slot_items[slot] = slot_item

                # Set data
                slot_item.setData(0, Qt.ItemDataRole.UserRole, slot)

                # Gray out if disabled
                if not slot.enabled:
                    for col in range(3):
                        slot_item.setForeground(col, QtGui.QColor(128, 128, 128))

    def get_selected_slot(self) -> Optional[HotkeySlot]:
        """Get the currently selected hotkey slot"""
        items = self.selectedItems()
        if not items:
            return None

        item = items[0]
        slot = item.data(0, Qt.ItemDataRole.UserRole)
        return slot if isinstance(slot, HotkeySlot) else None

    def update_slot_display(self, slot: HotkeySlot):
        """Update the display for a specific slot"""
        item = self._slot_items.get(slot)
        if item is None:
            return

        hotkeys_str = ", ".join(slot.assigned) if slot.assigned else "(none)"
        item.setText(1, hotkeys_str)


class HotkeyManagerUI(QtWidgets.QWidget):
    """UI for managing hotkeys"""

    def __init__(self, manager: HotkeyManager, parent=None):
        super().__init__(parent)
        self.manager = manager

        self.setWindowTitle("Hotkey Manager")
        self.setMinimumSize(900, 600)

        self._setup_ui()
        self._connect_signals()
        self._update_tree()

    def _setup_ui(self):
        """Setup the UI components"""
        layout = QtWidgets.QVBoxLayout(self)

        # Info label
        info_label = QtWidgets.QLabel(
            "Select an action below to view or modify its hotkeys. "
            "Multiple hotkeys can be assigned to the same action."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Tree widget
        self.tree = HotkeyTreeWidget()
        layout.addWidget(self.tree)

        # Details section
        details_group = QtWidgets.QGroupBox("Hotkey Details")
        details_layout = QtWidgets.QVBoxLayout(details_group)

        # Action name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("Action:"))
        self.action_label = QtWidgets.QLabel("")
        self.action_label.setFont(QtGui.QFont("", -1, QtGui.QFont.Weight.Bold))
        name_layout.addWidget(self.action_label)
        name_layout.addStretch()
        details_layout.addLayout(name_layout)

        # Description
        desc_layout = QtWidgets.QHBoxLayout()
        desc_layout.addWidget(QtWidgets.QLabel("Description:"))
        self.description_label = QtWidgets.QLabel("")
        self.description_label.setWordWrap(True)
        desc_layout.addWidget(self.description_label)
        desc_layout.addStretch()
        details_layout.addLayout(desc_layout)

        # Current hotkeys list
        hotkeys_layout = QtWidgets.QVBoxLayout()
        hotkeys_layout.addWidget(QtWidgets.QLabel("Current Hotkeys:"))
        self.hotkeys_list = QtWidgets.QListWidget()
        self.hotkeys_list.setMaximumHeight(100)
        hotkeys_layout.addWidget(self.hotkeys_list)
        details_layout.addLayout(hotkeys_layout)

        # Hotkey editing controls
        edit_layout = QtWidgets.QHBoxLayout()

        # Key capture
        self.key_capture = KeySequenceCapture()
        edit_layout.addWidget(self.key_capture, stretch=1)

        # Buttons
        self.assign_btn = QtWidgets.QPushButton("Assign")
        self.assign_btn.setToolTip("Replace all hotkeys with the captured one")
        edit_layout.addWidget(self.assign_btn)

        self.append_btn = QtWidgets.QPushButton("Add")
        self.append_btn.setToolTip("Add the captured hotkey to the list")
        edit_layout.addWidget(self.append_btn)

        self.remove_btn = QtWidgets.QPushButton("Remove")
        self.remove_btn.setToolTip("Remove the selected hotkey from the list")
        edit_layout.addWidget(self.remove_btn)

        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.setToolTip("Remove all hotkeys for this action")
        edit_layout.addWidget(self.clear_btn)

        self.reset_btn = QtWidgets.QPushButton("Reset to Default")
        self.reset_btn.setToolTip("Restore the default hotkeys")
        edit_layout.addWidget(self.reset_btn)

        details_layout.addLayout(edit_layout)

        layout.addWidget(details_group)

        # Bottom buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setToolTip("Save hotkey configuration to file")
        button_layout.addWidget(self.save_btn)

        self.close_btn = QtWidgets.QPushButton("Close")
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Initially disable editing controls
        self._set_editing_enabled(False)

    def _connect_signals(self):
        """Connect signals to slots"""
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.hotkeys_list.itemSelectionChanged.connect(self._on_hotkey_selected)

        self.key_capture.keySequenceCaptured.connect(self._on_key_captured)

        self.assign_btn.clicked.connect(self._on_assign_clicked)
        self.append_btn.clicked.connect(self._on_append_clicked)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        self.reset_btn.clicked.connect(self._on_reset_clicked)

        self.save_btn.clicked.connect(self._on_save_clicked)
        self.close_btn.clicked.connect(self.close)

    def _update_tree(self):
        """Update the tree display"""
        self.tree.populate_from_manager(self.manager)

    def _on_selection_changed(self):
        """Handle selection change in tree"""
        slot = self.tree.get_selected_slot()

        if slot is None:
            self._set_editing_enabled(False)
            self.action_label.setText("")
            self.description_label.setText("")
            self.hotkeys_list.clear()
            return

        # Update UI
        self._set_editing_enabled(True)
        self.action_label.setText(slot.name)
        self.description_label.setText(slot.description or "(No description)")

        # Update hotkeys list
        self.hotkeys_list.clear()
        for hotkey in slot.assigned:
            self.hotkeys_list.addItem(hotkey)

        # Update button states
        self._update_button_states()

    def _on_hotkey_selected(self):
        """Handle selection in hotkeys list"""
        self._update_button_states()

    def _on_key_captured(self, hotkey: str):
        """Handle key sequence capture"""
        self._update_button_states()

    def _update_button_states(self):
        """Update enabled state of buttons"""
        slot = self.tree.get_selected_slot()
        has_slot = slot is not None
        has_captured = bool(self.key_capture.text())
        has_hotkey_selected = bool(self.hotkeys_list.selectedItems())
        has_hotkeys = slot is not None and len(slot.assigned) > 0

        self.assign_btn.setEnabled(has_slot and has_captured)
        self.append_btn.setEnabled(has_slot and has_captured)
        self.remove_btn.setEnabled(has_slot and has_hotkey_selected)
        self.clear_btn.setEnabled(has_slot and has_hotkeys)
        self.reset_btn.setEnabled(has_slot)

    def _set_editing_enabled(self, enabled: bool):
        """Enable/disable editing controls"""
        self.key_capture.setEnabled(enabled)
        self._update_button_states()

    def _on_assign_clicked(self):
        """Assign the captured hotkey (replacing all others)"""
        slot = self.tree.get_selected_slot()
        captured = self.key_capture.text()

        if not slot or not captured:
            return

        # Check for conflicts
        conflict = self._check_conflict(captured, exclude_slot=slot)
        if conflict:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Hotkey Conflict",
                f"The hotkey '{captured}' is already assigned to '{conflict.name}'.\n\n"
                f"Do you want to remove it from '{conflict.name}' and assign it to '{slot.name}'?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
            # Remove from conflicting slot
            conflict.assigned = [h for h in conflict.assigned if h != captured]
            self.tree.update_slot_display(conflict)

        # Assign to current slot (replacing all)
        slot.assigned = [captured]

        # Update UI
        self.tree.update_slot_display(slot)
        self.hotkeys_list.clear()
        self.hotkeys_list.addItem(captured)
        self.key_capture.clear()
        self._update_button_states()

    def _on_append_clicked(self):
        """Add the captured hotkey to the list"""
        slot = self.tree.get_selected_slot()
        captured = self.key_capture.text()

        if not slot or not captured:
            return

        # Check if already assigned to this slot
        if captured in slot.assigned:
            QtWidgets.QMessageBox.information(
                self,
                "Already Assigned",
                f"The hotkey '{captured}' is already assigned to this action."
            )
            return

        # Check for conflicts
        conflict = self._check_conflict(captured, exclude_slot=slot)
        if conflict:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Hotkey Conflict",
                f"The hotkey '{captured}' is already assigned to '{conflict.name}'.\n\n"
                f"Do you want to remove it from '{conflict.name}' and add it to '{slot.name}'?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
            # Remove from conflicting slot
            conflict.assigned = [h for h in conflict.assigned if h != captured]
            self.tree.update_slot_display(conflict)

        # Add to current slot
        slot.assigned.append(captured)

        # Update UI
        self.tree.update_slot_display(slot)
        self.hotkeys_list.addItem(captured)
        self.key_capture.clear()
        self._update_button_states()

    def _on_remove_clicked(self):
        """Remove the selected hotkey"""
        slot = self.tree.get_selected_slot()
        items = self.hotkeys_list.selectedItems()

        if not slot or not items:
            return

        hotkey = items[0].text()

        # Remove from slot
        slot.assigned = [h for h in slot.assigned if h != hotkey]

        # Update UI
        self.tree.update_slot_display(slot)
        self.hotkeys_list.takeItem(self.hotkeys_list.row(items[0]))
        self._update_button_states()

    def _on_clear_clicked(self):
        """Clear all hotkeys for the selected action"""
        slot = self.tree.get_selected_slot()

        if not slot:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear All Hotkeys",
            f"Are you sure you want to remove all hotkeys for '{slot.name}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            slot.assigned = []
            self.tree.update_slot_display(slot)
            self.hotkeys_list.clear()
            self._update_button_states()

    def _on_reset_clicked(self):
        """Reset to default hotkeys"""
        slot = self.tree.get_selected_slot()

        if not slot:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset to Default",
            f"Are you sure you want to reset '{slot.name}' to its default hotkeys?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            slot.assigned = slot.default.copy()
            self.tree.update_slot_display(slot)

            # Update hotkeys list
            self.hotkeys_list.clear()
            for hotkey in slot.assigned:
                self.hotkeys_list.addItem(hotkey)

            self._update_button_states()

    def _on_save_clicked(self):
        """Save hotkey configuration"""
        if self.manager.hotkeys_file is None:
            QtWidgets.QMessageBox.warning(
                self,
                "No File Configured",
                "No hotkeys file has been configured for saving."
            )
            return

        try:
            # Build JSON structure
            data = {}
            for group in self.manager.hotkey_groups:
                group_data = []
                for slot in group.slots:
                    group_data.append({
                        "name": slot.name,
                        "assigned": slot.assigned
                    })
                data[group.name] = group_data

            # Save to file
            import json
            with open(self.manager.hotkeys_file, 'w') as f:
                json.dump(data, f, indent=2)

            QtWidgets.QMessageBox.information(
                self,
                "Saved",
                f"Hotkey configuration saved to {self.manager.hotkeys_file}"
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save hotkey configuration:\n{e}"
            )

    def _check_conflict(self, hotkey: str, exclude_slot: Optional[HotkeySlot] = None) -> Optional[HotkeySlot]:
        """Check if a hotkey is already assigned to another slot

        Args:
            hotkey: The hotkey string to check
            exclude_slot: Slot to exclude from the check (typically the one being edited)

        Returns:
            The conflicting HotkeySlot, or None if no conflict
        """
        for group in self.manager.hotkey_groups:
            for slot in group.slots:
                if slot == exclude_slot:
                    continue
                if hotkey in slot.assigned:
                    return slot
        return None


def show_hotkey_manager(manager: HotkeyManager, parent=None) -> HotkeyManagerUI:
    """Convenience function to create and show the hotkey manager UI"""
    ui = HotkeyManagerUI(manager, parent)
    ui.show()
    return ui
