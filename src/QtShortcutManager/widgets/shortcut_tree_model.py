from __future__ import annotations
from typing import TYPE_CHECKING

from Qt.QtCore import Qt, QSortFilterProxyModel, QModelIndex
from Qt.QtGui import QStandardItemModel, QStandardItem, QFont
from Qt.QtGui import QKeySequence

if TYPE_CHECKING:
    from ..shortcut_manager import ShortcutManager, ShortcutSlot


class ShortcutTreeModel(QStandardItemModel):
    """Model for the shortcut tree view.

    Tree structure:
        - Group Item (bold) - represents ShortcutSlotGroup
          - Slot Item - represents ShortcutSlot
          - Slot Item
          ...
        - Group Item
          ...
    """

    # Custom data roles
    ROLE_ITEM_TYPE = Qt.UserRole
    ROLE_GROUP_NAME = Qt.UserRole + 1
    ROLE_SLOT_DATA = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Command", "Shortcut", "Description"])

    def populate_from_manager(self, manager: ShortcutManager):
        """Build tree structure from ShortcutManager.

        Args:
            manager: The ShortcutManager to display
        """
        self.clear()
        self.setHorizontalHeaderLabels(["Command", "Shortcut", "Description"])
        self._populate_groups_recursive(manager.shortcut_groups, None, "")

    def _populate_groups_recursive(
        self, groups: list, parent_item: QStandardItem | None, parent_path: str
    ):
        """Recursively populate groups and their slots

        Args:
            groups: List of ShortcutSlotGroups to populate
            parent_item: The parent QStandardItem (None for root level)
            parent_path: The path of the parent group (empty string for root)
        """
        for group in groups:
            # Build the full path for this group
            if parent_path:
                group_path = f"{parent_path}.{group.name}"
            else:
                group_path = group.name

            # Create group items
            group_items = self._create_group_items(group.name, group_path)

            # Add slots to this group
            for slot in group.slots:
                slot_items = self._create_slot_items(slot, group_path)
                group_items[0].appendRow(slot_items)

            # Recursively add nested groups
            if hasattr(group, "groups") and group.groups:
                self._populate_groups_recursive(group.groups, group_items[0], group_path)

            # Add group to parent or root
            if parent_item is None:
                self.appendRow(group_items)
            else:
                parent_item.appendRow(group_items)

    def _create_group_items(
        self, group_name: str, group_path: str
    ) -> list[QStandardItem]:
        """Create row items for a group.

        Args:
            group_name: The display name of the group
            group_path: The full path of the group (e.g., "parent.child")

        Returns:
            List of [name_item, shortcut_item, description_item] for the group row
        """
        name_item = QStandardItem(group_name)
        name_item.setData("group", self.ROLE_ITEM_TYPE)
        name_item.setData(group_path, self.ROLE_GROUP_NAME)
        name_item.setEditable(False)

        # Make group text bold
        font = QFont()
        font.setBold(True)
        name_item.setFont(font)

        shortcut_item = QStandardItem("")
        shortcut_item.setEditable(False)

        description_item = QStandardItem("")
        description_item.setEditable(False)

        return [name_item, shortcut_item, description_item]

    def _create_slot_items(
        self, slot: ShortcutSlot, group_name: str
    ) -> list[QStandardItem]:
        """Create row items for a slot.

        Args:
            slot: The ShortcutSlot to display
            group_name: The name of the parent group

        Returns:
            List of [name_item, shortcut_item, description_item] for the slot row
        """
        name_item = QStandardItem(slot.name)
        name_item.setData("slot", self.ROLE_ITEM_TYPE)
        name_item.setData(group_name, self.ROLE_GROUP_NAME)
        name_item.setData(slot, self.ROLE_SLOT_DATA)
        name_item.setEditable(False)

        # Build shortcut display text
        shortcut_text = self._format_shortcuts(slot.assigned)

        shortcut_item = QStandardItem(shortcut_text)
        shortcut_item.setEditable(False)
        shortcut_item.setData(slot, self.ROLE_SLOT_DATA)

        # Description column
        description_item = QStandardItem(slot.desc)
        description_item.setEditable(False)
        description_item.setData(slot, self.ROLE_SLOT_DATA)

        return [name_item, shortcut_item, description_item]

    def _format_shortcuts(self, sequences: list[QKeySequence]) -> str:
        """Format list of key sequences for display.

        Uses semicolon to separate multiple shortcuts, while comma separates
        multi-key combinations within a single shortcut.

        Args:
            sequences: List of QKeySequence objects

        Returns:
            Formatted string like "Ctrl+C; Ctrl+Shift+C" or "Ctrl+K, Ctrl+C" or "<None>"
        """
        if not sequences:
            return "<None>"

        # Use semicolon separator to differentiate from comma (used within multi-key sequences)
        return " ; ".join(seq.toString(QKeySequence.NativeText) for seq in sequences)

    def update_slot_shortcuts(self, group_path: str, slot: ShortcutSlot):
        """Update the shortcut display for a specific slot.

        Args:
            group_path: The full path of the group containing the slot
            slot: The ShortcutSlot to update
        """
        slot_item = self._find_slot_item(group_path, slot)
        if slot_item:
            # Update shortcut column (column 1)
            shortcut_text = self._format_shortcuts(slot.assigned)
            parent_item = slot_item.parent()
            slot_row = slot_item.row()
            shortcut_col_item = parent_item.child(slot_row, 1)
            shortcut_col_item.setText(shortcut_text)

    def _find_slot_item(
        self, group_path: str, slot: ShortcutSlot
    ) -> QStandardItem | None:
        """Find the tree item for a specific slot.

        Args:
            group_path: The full path of the group containing the slot
            slot: The ShortcutSlot to find

        Returns:
            The QStandardItem for the slot, or None if not found
        """
        return self._find_slot_item_recursive(self.invisibleRootItem(), group_path, slot)

    def _find_slot_item_recursive(
        self, parent_item: QStandardItem, group_path: str, slot: ShortcutSlot
    ) -> QStandardItem | None:
        """Recursively search for a slot item in the tree.

        Args:
            parent_item: The parent item to search within
            group_path: The full path of the group containing the slot
            slot: The ShortcutSlot to find

        Returns:
            The QStandardItem for the slot, or None if not found
        """
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row, 0)
            if item is None:
                continue

            item_type = item.data(self.ROLE_ITEM_TYPE)

            if item_type == "group":
                # Check if this is the group we're looking for
                if item.data(self.ROLE_GROUP_NAME) == group_path:
                    # Search children for matching slot
                    for slot_row in range(item.rowCount()):
                        slot_item = item.child(slot_row, 0)
                        if (
                            slot_item
                            and slot_item.data(self.ROLE_ITEM_TYPE) == "slot"
                            and slot_item.data(self.ROLE_SLOT_DATA) is slot
                        ):
                            return slot_item

                # Recursively search nested groups
                result = self._find_slot_item_recursive(item, group_path, slot)
                if result:
                    return result

        return None


class ShortcutFilterProxyModel(QSortFilterProxyModel):
    """Proxy model for filtering shortcuts based on search criteria.

    Filters on:
        - Slot names (case-insensitive)
        - Descriptions (case-insensitive)
        - Key sequences (case-insensitive)
        - Group names (case-insensitive)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str):
        """Update filter text and refresh the view.

        Args:
            text: The search text to filter by
        """
        self._filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Determine if a row should be shown.

        Args:
            source_row: Row index in source model
            source_parent: Parent index in source model

        Returns:
            True if row should be shown, False otherwise
        """
        if not self._filter_text:
            return True  # No filter, show all

        source_model = self.sourceModel()
        if not isinstance(source_model, ShortcutTreeModel):
            return True

        index = source_model.index(source_row, 0, source_parent)
        item = source_model.itemFromIndex(index)
        if not item:
            return True

        item_type = item.data(ShortcutTreeModel.ROLE_ITEM_TYPE)

        if item_type == "group":
            # For groups: check group name OR any child slot
            group_name = item.text().lower()
            if self._filter_text in group_name:
                return True

            # Check if any child matches
            for row in range(item.rowCount()):
                if self.filterAcceptsRow(row, index):
                    return True
            return False

        elif item_type == "slot":
            # For slots: check name, description, shortcuts
            slot = item.data(ShortcutTreeModel.ROLE_SLOT_DATA)
            if not slot:
                return False

            # Check slot name
            if self._filter_text in slot.name.lower():
                return True

            # Check description
            if self._filter_text in slot.desc.lower():
                return True

            # Check assigned shortcuts
            for keyseq in slot.assigned:
                seq_str = keyseq.toString(QKeySequence.NativeText).lower()
                if self._filter_text in seq_str:
                    return True

            return False

        return True
