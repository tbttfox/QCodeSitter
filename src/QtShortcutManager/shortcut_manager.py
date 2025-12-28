from __future__ import annotations
from typing import Callable, Optional, TYPE_CHECKING
from inspect import getdoc
from pathlib import Path
import json

from Qt.QtGui import QKeySequence
from Qt.QtWidgets import QAction

if TYPE_CHECKING:
    from Qt.QtWidgets import QWidget


class ShortcutSlot:
    """A class defining possible shortcut slots as part of the ShortcutManager"""

    def __init__(
        self,
        name: str,
        targetFunc: Callable[[], None],
        defaults: list[QKeySequence],
        desc: Optional[str] = None,
        assigned: Optional[list[QKeySequence]] = None,
        enabled: bool = True,
    ):
        self.name: str = name
        self.desc: str = desc or getdoc(targetFunc) or "<No Description>"
        self.targetFunc: Callable[[], None] = targetFunc
        self.defaults = defaults
        self.action: Optional[QAction] = None
        self.enabled = enabled
        # Store assignments regardless of enabled state
        self.assigned: list[QKeySequence] = assigned or self.defaults[:]

    def unload(self):
        self.action = None
        self.targetFunc = lambda: None

    def load(self, assignedData: list[str], parent: Optional[QWidget] = None):
        from Qt.QtCore import Qt
        self.action = QAction(parent)
        seqs = [QKeySequence(key, QKeySequence.PortableText) for key in assignedData]
        self.action.setShortcuts(seqs)
        self.action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action.triggered.connect(self.targetFunc)
        # Add the action to the parent widget so shortcuts are active
        if parent is not None:
            parent.addAction(self.action)


class ShortcutSlotGroup:
    """A group of related shortcut slots"""

    def __init__(self, name, slots: Optional[list[ShortcutSlot]] = None):
        self.name = name
        self.slots: list[ShortcutSlot] = slots or []

    def unload(self):
        for slot in self.slots:
            slot.unload()


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

    def load_user_shortcut(self, prefs: dict[str, dict[str, list[str]]]):
        """Load the user-defined shortcut from the given prefs dict
        The prefs dict is formatted like:
            {
                "groupName": {
                    "slotName": ['keySeq1', 'keySeq2', ...],
                    ...
                },
                ...
            }
        """
        groups_by_name: dict[str, ShortcutSlotGroup] = {
            g.name: g for g in self.shortcut_groups
        }
        for group_name, slot_datas in prefs.items():
            group = groups_by_name.get(group_name)
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
                # Load the shortcuts (assigned list already contains the converted sequences)
                slot.load(assigned)

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
                ...
            }
        """
        prefs: dict[str, dict[str, list[str]]] = {}
        for group in self.shortcut_groups:
            prefs[group.name] = {}
            for slot in group.slots:
                prefs[group.name][slot.name] = [
                    seq.toString(QKeySequence.PortableText) for seq in slot.assigned
                ]
        return prefs
