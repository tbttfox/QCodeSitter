from __future__ import annotations

from Qt.QtCore import Qt
from Qt.QtGui import QKeySequence
from Qt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeView,
    QLabel,
    QFrame,
    QDialogButtonBox,
    QMessageBox,
)

from .shortcut_manager import ShortcutManager, ShortcutSlot, ShortcutSlotGroup
from .widgets import (
    ShortcutTreeModel,
    ShortcutFilterProxyModel,
    ShortcutDetailsPanel,
    SearchFilterWidget,
)
from .utils import ConflictDetector


def _pluralize(count: int, singular: str, plural: str = None) -> str:
    """Helper function to pluralize words based on count.

    Args:
        count: The number to check
        singular: The singular form of the word
        plural: The plural form (if None, adds 's' to singular)

    Returns:
        The appropriate word form
    """
    if count == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


class ShortcutManagerDialog(QDialog):
    """Main dialog for managing keyboard shortcuts.

    Features:
        - Tree view of shortcut groups and slots
        - Search/filter functionality
        - Details panel for editing shortcuts
        - Conflict detection
        - Save/Apply/Cancel workflow with dirty tracking
    """

    def __init__(self, shortcut_manager: ShortcutManager, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Shortcut Manager")
        self.resize(900, 600)

        # Store original manager (read-only during editing)
        self._original_manager = shortcut_manager

        # Create working copy for editing
        self._working_manager = self._deep_copy_manager(shortcut_manager)

        # Dirty state tracking
        self._dirty = False
        self._modified_slots: set[tuple[str, str]] = set()

        # Conflict detector
        self._conflict_detector = ConflictDetector()
        self._conflict_detector.build_from_manager(self._working_manager)

        # Track expansion state
        self._is_filtering = False

        # Build UI
        self._setup_ui()

        # Populate tree from working copy
        self._tree_model.populate_from_manager(self._working_manager)

        # Expand all groups by default
        self._tree_view.expandAll()

        # Resize columns to fit contents with some padding
        self._resize_columns_with_padding(padding=20)

        # Update button states
        self._update_button_states()

    def _setup_ui(self):
        """Build the dialog UI."""
        main_layout = QVBoxLayout(self)

        # Search bar at top
        self._search_widget = SearchFilterWidget()
        self._search_widget.filterChanged.connect(self._on_filter_changed)
        main_layout.addWidget(self._search_widget)

        # Splitter for tree + details
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Tree view
        self._tree_model = ShortcutTreeModel()
        self._proxy_model = ShortcutFilterProxyModel()
        self._proxy_model.setSourceModel(self._tree_model)

        self._tree_view = QTreeView()
        self._tree_view.setModel(self._proxy_model)
        self._tree_view.setMinimumWidth(250)
        self._tree_view.setAlternatingRowColors(True)
        self._tree_view.setHeaderHidden(False)
        self._tree_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        splitter.addWidget(self._tree_view)

        # Right side: Details panel
        self._details_panel = ShortcutDetailsPanel()
        self._details_panel.setMinimumWidth(300)
        self._details_panel.shortcutsChanged.connect(self._on_shortcuts_changed)
        splitter.addWidget(self._details_panel)

        # Set splitter proportions: 40% tree, 60% details
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        # Set initial sizes - right panel starts at minimum width
        splitter.setSizes([600, 300])

        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self._status_label = QLabel("Ready")
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        status_layout = QHBoxLayout(status_frame)
        status_layout.addWidget(self._status_label)
        status_layout.setContentsMargins(4, 2, 4, 2)
        main_layout.addWidget(status_frame)

        # Button box at bottom
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel
        )
        self._button_box.accepted.connect(self._on_save)
        self._button_box.rejected.connect(self._on_cancel)

        self._apply_button = self._button_box.button(QDialogButtonBox.Apply)
        self._apply_button.clicked.connect(self._on_apply)
        self._apply_button.setEnabled(False)

        main_layout.addWidget(self._button_box)

    def _resize_columns_with_padding(self, padding: int = 20):
        """Resize all tree view columns to fit content with added padding.

        Args:
            padding: Extra width to add to each column (default: 20)
        """
        for column in range(self._tree_model.columnCount()):
            self._tree_view.resizeColumnToContents(column)
            self._tree_view.setColumnWidth(
                column, self._tree_view.columnWidth(column) + padding
            )

    @staticmethod
    def _copy_keysequence(keyseq: QKeySequence) -> QKeySequence:
        """Create a deep copy of a QKeySequence.

        Args:
            keyseq: The QKeySequence to copy

        Returns:
            A new QKeySequence with the same value
        """
        return QKeySequence(keyseq.toString(QKeySequence.PortableText))

    def _deep_copy_manager(self, manager: ShortcutManager) -> ShortcutManager:
        """Create a deep copy of ShortcutManager for editing.

        Copies all shortcut data for editing.

        Args:
            manager: The ShortcutManager to copy

        Returns:
            A deep copy of the manager
        """
        new_manager = ShortcutManager(manager.shortcut_file)
        new_manager.shortcut_groups = self._deep_copy_groups(manager.shortcut_groups)
        return new_manager

    def _deep_copy_groups(
        self, groups: list[ShortcutSlotGroup]
    ) -> list[ShortcutSlotGroup]:
        """Recursively deep copy a list of ShortcutSlotGroups

        Args:
            groups: List of groups to copy

        Returns:
            Deep copied list of groups
        """
        new_groups = []
        for group in groups:
            new_slots = []
            for slot in group.slots:
                # Create new slot with copied data
                new_slot = ShortcutSlot(
                    name=slot.name,
                    defaults=slot.defaults[:],  # Shallow copy list
                    desc=slot.desc,
                    assigned=[self._copy_keysequence(seq) for seq in slot.assigned],
                    enabled=slot.enabled,
                )
                new_slots.append(new_slot)

            # Recursively copy nested groups
            new_nested_groups = []
            if hasattr(group, "groups") and group.groups:
                new_nested_groups = self._deep_copy_groups(group.groups)

            new_group = ShortcutSlotGroup(group.name, new_slots, new_nested_groups)
            new_groups.append(new_group)

        return new_groups

    def _on_selection_changed(self):
        """Handle tree view selection changes."""
        indexes = self._tree_view.selectionModel().selectedIndexes()
        if not indexes:
            self._details_panel._set_empty_state()
            return

        # Get the first column index (name column)
        index = indexes[0]

        # Map from proxy to source model
        source_index = self._proxy_model.mapToSource(index)
        item = self._tree_model.itemFromIndex(source_index)

        if not item:
            return

        item_type = item.data(ShortcutTreeModel.ROLE_ITEM_TYPE)

        if item_type == "slot":
            # Show slot details
            slot = item.data(ShortcutTreeModel.ROLE_SLOT_DATA)
            group_name = item.data(ShortcutTreeModel.ROLE_GROUP_NAME)

            if slot and group_name:
                self._details_panel.set_slot(group_name, slot)
                self._check_and_display_conflicts(group_name, slot)
        else:
            # Group selected - show empty state
            self._details_panel._set_empty_state()

    def _on_shortcuts_changed(self, group_name: str, slot: ShortcutSlot):
        """Handle changes to a slot's shortcuts.

        Args:
            group_name: The group containing the modified slot
            slot: The modified slot
        """
        # Mark as dirty
        self._mark_dirty(group_name, slot.name)

        # Update tree display
        self._tree_model.update_slot_shortcuts(group_name, slot)

        # Rebuild conflict detector
        self._conflict_detector.build_from_manager(self._working_manager)

        # Check for conflicts
        self._check_and_display_conflicts(group_name, slot)

        # Update status
        self._update_status()

    def _check_and_display_conflicts(self, group_name: str, slot: ShortcutSlot):
        """Check for conflicts in a slot and update display.

        Args:
            group_name: The group containing the slot
            slot: The slot to check
        """
        conflicts = []

        for keyseq in slot.assigned:
            conflict = self._conflict_detector.check_conflict(
                keyseq, group_name, slot.name
            )
            if conflict:
                conflicts.extend(conflict)

        # Remove duplicates
        unique_conflicts = list(set(conflicts))

        if unique_conflicts:
            self._details_panel.show_conflicts(unique_conflicts)
        else:
            self._details_panel.clear_conflicts()

    def _mark_dirty(self, group_name: str, slot_name: str):
        """Mark a slot as modified.

        Args:
            group_name: The group name
            slot_name: The slot name
        """
        self._modified_slots.add((group_name, slot_name))
        self._dirty = True
        self._update_button_states()

    def _update_button_states(self):
        """Update Apply button enabled state based on dirty flag and conflicts."""
        has_conflicts = bool(self._conflict_detector.get_all_conflicts())
        self._apply_button.setEnabled(self._dirty and not has_conflicts)

    def _update_status(self):
        """Update status bar text."""
        modified_count = len(self._modified_slots)
        conflict_count = len(self._conflict_detector.get_all_conflicts())

        status_parts = []

        if modified_count > 0:
            status_parts.append(
                f"{modified_count} {_pluralize(modified_count, 'shortcut')} modified"
            )

        if conflict_count > 0:
            status_parts.append(
                f"{conflict_count} {_pluralize(conflict_count, 'conflict')}"
            )

        if status_parts:
            self._status_label.setText(", ".join(status_parts))
        else:
            self._status_label.setText("Ready")

    def _has_unresolved_conflicts(self) -> bool:
        """Check if there are any unresolved conflicts.

        Returns:
            True if conflicts exist, False otherwise
        """
        return bool(self._conflict_detector.get_all_conflicts())

    def _on_apply(self):
        """Apply changes to original manager."""
        if self._has_unresolved_conflicts():
            QMessageBox.warning(
                self,
                "Cannot Apply Changes",
                "Please resolve all shortcut conflicts before applying changes.",
            )
            return

        # Apply changes to original manager
        self._apply_changes_to_original()

        # Save to file if configured
        if self._original_manager.shortcut_file:
            try:
                self._original_manager.save_user_shortcut_to_file()
            except Exception as e:
                QMessageBox.critical(
                    self, "Save Error", f"Failed to save shortcuts to file:\n{e}"
                )
                return

        # Clear dirty state
        self._dirty = False
        self._modified_slots.clear()
        self._update_button_states()
        self._update_status()

        QMessageBox.information(
            self, "Changes Applied", "Shortcut changes have been applied successfully."
        )

    def _apply_changes_to_original(self):
        """Copy working manager data back to original manager."""
        # Build path maps for both managers
        orig_groups_by_path = self._original_manager._build_group_path_map()
        work_groups_by_path = self._working_manager._build_group_path_map()

        # Copy changes from working to original
        for group_path, work_group in work_groups_by_path.items():
            orig_group = orig_groups_by_path.get(group_path)
            if not orig_group:
                continue

            orig_slots = {s.name: s for s in orig_group.slots}

            for work_slot in work_group.slots:
                orig_slot = orig_slots.get(work_slot.name)
                if not orig_slot:
                    continue

                # Copy assigned shortcuts
                orig_slot.assigned = [
                    self._copy_keysequence(seq) for seq in work_slot.assigned
                ]

                # Copy enabled state
                orig_slot.enabled = work_slot.enabled

    def _on_save(self):
        """Apply changes and close dialog."""
        self._on_apply()
        if not self._dirty:  # Only close if apply succeeded
            self.accept()

    def _on_cancel(self):
        """Discard changes and close dialog."""
        if self._dirty:
            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Are you sure you want to discard them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if result == QMessageBox.No:
                return

        self.reject()

    def _on_filter_changed(self, text: str):
        """Handle search filter text changes.

        Args:
            text: The new filter text
        """
        # If we're starting to filter, save current expansion state
        if text and not self._is_filtering:
            self._saved_expansion_state = self._get_expansion_state()
            self._is_filtering = True

        self._proxy_model.set_filter_text(text)

        if text:
            # Expand all groups when filtering to show results
            self._tree_view.expandAll()
        else:
            # Restore previous expansion state when filter is cleared
            if self._is_filtering and hasattr(self, "_saved_expansion_state"):
                self._restore_expansion_state(self._saved_expansion_state)
            self._is_filtering = False

    def _get_expansion_state(self) -> dict[str, bool]:
        """Get current expansion state of all groups.

        Returns:
            Dictionary mapping group names to their expanded state
        """
        state = {}
        model = self._tree_model

        for row in range(model.rowCount()):
            group_item = model.item(row, 0)
            if group_item:
                group_name = group_item.data(ShortcutTreeModel.ROLE_GROUP_NAME)
                if group_name:
                    # Map from source to proxy model
                    source_index = model.indexFromItem(group_item)
                    proxy_index = self._proxy_model.mapFromSource(source_index)
                    state[group_name] = self._tree_view.isExpanded(proxy_index)

        return state

    def _restore_expansion_state(self, state: dict[str, bool]):
        """Restore expansion state of groups.

        Args:
            state: Dictionary mapping group names to their expanded state
        """
        model = self._tree_model

        for row in range(model.rowCount()):
            group_item = model.item(row, 0)
            if group_item:
                group_name = group_item.data(ShortcutTreeModel.ROLE_GROUP_NAME)
                if group_name and group_name in state:
                    source_index = model.indexFromItem(group_item)
                    proxy_index = self._proxy_model.mapFromSource(source_index)
                    self._tree_view.setExpanded(proxy_index, state[group_name])
