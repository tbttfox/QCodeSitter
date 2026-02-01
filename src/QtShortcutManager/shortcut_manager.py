from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from pathlib import Path
import json

from Qt.QtGui import QKeySequence

if TYPE_CHECKING:
    pass


class ShortcutSlot:
    """A class defining possible shortcut slots as part of the ShortcutManager

    ShortcutSlots are designed to be defined as class properties on objects that
    will use them. This allows inspection and editing of shortcuts without
    instantiating the class. The actual QAction creation and signal connection
    is the responsibility of the class using these slots.
    """

    def __init__(
        self,
        name: str,
        method_name: str,
        defaults: list[QKeySequence],
        desc: str = "<No Description>",
        assigned: Optional[list[QKeySequence]] = None,
        enabled: bool = True,
    ):
        self.name: str = name
        self.method_name: str = method_name
        self.desc: str = desc
        self.defaults = defaults
        self.enabled = enabled
        # Store assignments regardless of enabled state
        self.assigned: list[QKeySequence] = assigned or self.defaults[:]


class ShortcutSlotGroup:
    """A group of related shortcut slots and/or nested groups

    ShortcutSlotGroups can contain both ShortcutSlots and other ShortcutSlotGroups,
    allowing for arbitrary nesting of shortcut organization.
    """

    def __init__(
        self,
        name: str,
        slots: Optional[list[ShortcutSlot]] = None,
        groups: Optional[list[ShortcutSlotGroup]] = None,
    ):
        self.name = name
        self.slots: list[ShortcutSlot] = slots or []
        self.groups: list[ShortcutSlotGroup] = groups or []


class ShortcutManager:
    def __init__(self, shortcut_file: Optional[Path] = None):
        self.shortcut_groups: list[ShortcutSlotGroup] = []
        self.shortcut_file: Optional[Path] = shortcut_file

    def load_user_shortcut_from_file(self):
        """Load user shortcuts from the configured JSON file"""
        if self.shortcut_file is None:
            return

        try:
            with self.shortcut_file.open() as f:
                prefs = json.load(f)
        except FileNotFoundError:
            # File doesn't exist yet - not an error, just use defaults
            return
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in shortcut file: {e}")

        self.load_user_shortcut(prefs)

    def load_user_shortcut(self, prefs: dict):
        """Load the user-defined shortcut from the given prefs dict
        The prefs dict is formatted like:
            {
                "groupName": {
                    "slotName": ['keySeq1', 'keySeq2', ...],
                    ...
                },
                "groupName.nestedGroupName": {
                    "slotName": ['keySeq1', 'keySeq2', ...],
                    ...
                },
                ...
            }
        Nested groups use dot notation in their keys (e.g., "parent.child.grandchild")
        """
        # Build a flat map of all groups by their full path
        groups_by_path = self._build_group_path_map()

        for group_path, slot_datas in prefs.items():
            group = groups_by_path.get(group_path)
            if group is None:
                continue
            slots_by_name = {s.name: s for s in group.slots}
            for slotName, assigned in slot_datas.items():
                slot = slots_by_name.get(slotName)
                if slot is None:
                    continue
                # Convert string keys to QKeySequence objects
                slot.assigned = [
                    QKeySequence(key, QKeySequence.PortableText) for key in assigned
                ]

    def save_user_shortcut_to_file(self):
        """Save current shortcuts to the configured JSON file"""
        if self.shortcut_file is None:
            return

        prefs = self.export_to_dict()
        with self.shortcut_file.open("w") as f:
            json.dump(prefs, f, indent=2)

    def export_to_dict(self) -> dict[str, dict[str, list[str]]]:
        """Export current shortcut state to dictionary format

        Returns:
            Dictionary formatted as:
            {
                "groupName": {
                    "slotName": ['keySeq1', 'keySeq2', ...],
                    ...
                },
                "groupName.nestedGroupName": {
                    "slotName": ['keySeq1', 'keySeq2', ...],
                    ...
                },
                ...
            }
        Nested groups use dot notation in their keys.
        """
        prefs: dict[str, dict[str, list[str]]] = {}
        self._export_group_recursive(self.shortcut_groups, "", prefs)
        return prefs

    def _export_group_recursive(
        self,
        groups: list[ShortcutSlotGroup],
        parent_path: str,
        prefs: dict[str, dict[str, list[str]]],
    ):
        """Recursively export groups and their slots to prefs dict

        Args:
            groups: List of groups to export
            parent_path: The path of the parent group (empty string for root)
            prefs: Dictionary to populate with exported data
        """
        for group in groups:
            # Build the full path for this group
            if parent_path:
                group_path = f"{parent_path}.{group.name}"
            else:
                group_path = group.name

            # Export slots for this group
            if group.slots:
                prefs[group_path] = {}
                for slot in group.slots:
                    prefs[group_path][slot.name] = [
                        seq.toString(QKeySequence.PortableText) for seq in slot.assigned
                    ]

            # Recursively export nested groups
            if group.groups:
                self._export_group_recursive(group.groups, group_path, prefs)

    def _build_group_path_map(
        self, groups: Optional[list[ShortcutSlotGroup]] = None, parent_path: str = ""
    ) -> dict[str, ShortcutSlotGroup]:
        """Build a flat map of all groups by their full path

        Args:
            groups: List of groups to process (defaults to root groups)
            parent_path: The path of the parent group (empty string for root)

        Returns:
            Dictionary mapping group paths to ShortcutSlotGroup objects
        """
        if groups is None:
            groups = self.shortcut_groups

        result: dict[str, ShortcutSlotGroup] = {}

        for group in groups:
            # Build the full path for this group
            if parent_path:
                group_path = f"{parent_path}.{group.name}"
            else:
                group_path = group.name

            result[group_path] = group

            # Recursively process nested groups
            if group.groups:
                nested_map = self._build_group_path_map(group.groups, group_path)
                result.update(nested_map)

        return result
