from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from Qt.QtGui import QKeySequence

if TYPE_CHECKING:
    from ..shortcut_manager import ShortcutManager


class ConflictDetector:
    """Detects conflicting keyboard shortcut assignments.

    Maintains a reverse mapping from key sequences to the slots they're assigned to,
    enabling efficient conflict detection when adding or modifying shortcuts.
    """

    def __init__(self):
        # Map: keysequence_string -> list of (group_name, slot_name)
        self._reverse_map: dict[str, list[tuple[str, str]]] = {}

    def build_from_manager(self, manager: ShortcutManager):
        """Build reverse mapping from ShortcutManager's current state.

        Args:
            manager: The ShortcutManager to analyze
        """
        self._reverse_map.clear()
        self._build_from_groups(manager.shortcut_groups, "")

    def _build_from_groups(self, groups: list, parent_path: str):
        """Recursively build reverse mapping from groups

        Args:
            groups: List of ShortcutSlotGroups to process
            parent_path: The path of the parent group (empty string for root)
        """
        from ..shortcut_manager import ShortcutSlotGroup

        for group in groups:
            # Build the full path for this group
            if parent_path:
                group_path = f"{parent_path}.{group.name}"
            else:
                group_path = group.name

            # Process slots in this group
            for slot in group.slots:
                for keyseq in slot.assigned:
                    self.add_assignment(keyseq, group_path, slot.name)

            # Recursively process nested groups
            if hasattr(group, "groups") and group.groups:
                self._build_from_groups(group.groups, group_path)

    def check_conflict(
        self, keyseq: QKeySequence, current_group: str, current_slot: str
    ) -> Optional[list[tuple[str, str]]]:
        """Check if assigning a key sequence would create a conflict.

        Args:
            keyseq: The key sequence to check
            current_group: The group name of the slot being assigned
            current_slot: The slot name being assigned

        Returns:
            List of conflicting (group_name, slot_name) tuples, or None if no conflicts
        """
        key_str = keyseq.toString(QKeySequence.PortableText)
        if not key_str:  # Empty sequence
            return None

        existing = self._reverse_map.get(key_str, [])

        # Filter out self-assignment (same group and slot)
        conflicts = [
            (g, s)
            for g, s in existing
            if not (g == current_group and s == current_slot)
        ]

        return conflicts if conflicts else None

    def add_assignment(self, keyseq: QKeySequence, group: str, slot: str):
        """Add a key sequence assignment to the tracking map.

        Args:
            keyseq: The key sequence being assigned
            group: The group name
            slot: The slot name
        """
        key_str = keyseq.toString(QKeySequence.PortableText)
        if not key_str:  # Ignore empty sequences
            return

        if key_str not in self._reverse_map:
            self._reverse_map[key_str] = []

        # Avoid duplicates
        assignment = (group, slot)
        if assignment not in self._reverse_map[key_str]:
            self._reverse_map[key_str].append(assignment)

    def remove_assignment(self, keyseq: QKeySequence, group: str, slot: str):
        """Remove a key sequence assignment from the tracking map.

        Args:
            keyseq: The key sequence being removed
            group: The group name
            slot: The slot name
        """
        key_str = keyseq.toString(QKeySequence.PortableText)
        if not key_str:
            return

        if key_str in self._reverse_map:
            self._reverse_map[key_str] = [
                (g, s)
                for g, s in self._reverse_map[key_str]
                if not (g == group and s == slot)
            ]

            # Clean up empty entries
            if not self._reverse_map[key_str]:
                del self._reverse_map[key_str]

    def clear(self):
        """Clear all tracked assignments."""
        self._reverse_map.clear()

    def get_all_conflicts(self) -> dict[str, list[tuple[str, str]]]:
        """Get all key sequences that have multiple assignments.

        Returns:
            Dictionary mapping key sequence strings to lists of conflicting
            (group_name, slot_name) tuples. Only includes sequences with
            2 or more assignments.
        """
        return {
            key: assignments
            for key, assignments in self._reverse_map.items()
            if len(assignments) > 1
        }
