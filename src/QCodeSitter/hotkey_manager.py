from __future__ import annotations
from typing import Callable, Union, Optional
from inspect import getdoc
from pathlib import Path
import json

from Qt.QtCore import Qt
from Qt.QtGui import QKeySequence
from Qt import QtCompat


def hk(
    key: Union[Qt.Key, int],
    mods: Optional[Union[Qt.KeyboardModifier, Qt.KeyboardModifiers, int]] = None,
) -> str:
    """Build a hashable hotkey string"""
    # Ignore pure modifier presses
    # And handle the stupidity of backtab
    kd = {
        Qt.Key_Shift: "Shift",
        Qt.Key_Control: "Control",
        Qt.Key_Alt: "Alt",
        Qt.Key_Meta: "Meta",
        Qt.Key_Backtab: "Shift+Tab",
    }
    single = kd.get(key)  # type: ignore
    if single is not None:
        return single

    seqval = int(key)
    if mods is not None:
        seqval |= QtCompat.enumValue(mods)

    return QKeySequence(seqval).toString(QKeySequence.PortableText)


class HotkeySlot:
    """Information about a function that can be called by a hotkey"""

    def __init__(
        self,
        name: str,
        slot: Callable,
        default: list[str],
        assigned: Optional[list[str]] = None,
        description: Optional[str] = None,
        enabled: bool = True,
    ):
        self.name: str = name
        self.slot: Callable = slot
        self.default: list[str] = default
        self.assigned: list[str] = default if assigned is None else assigned
        self.description: str = (
            getdoc(self.slot) if description is None else description
        )
        self.enabled = enabled


class HotkeyGroup:
    def __init__(self, name: str, slots: Optional[list[HotkeySlot]]):
        self.name: str = name
        self.slots: list[HotkeySlot] = slots or []


class HotkeyManager:
    def __init__(self, hotkeys_file: Optional[Path] = None):
        self.hotkey_groups: list[HotkeyGroup] = []
        self.hotkeys_file: Optional[Path] = hotkeys_file

    def load_user_hotkeys(self):
        if self.hotkeys_file is None:
            return

        with self.hotkeys_file.open() as f:
            prefs = json.load(f)

        groups_by_name = {g.name: g for g in self.hotkey_groups}
        for group_name, slot_datas in prefs.items():
            if group_name not in groups_by_name:
                continue
            group = groups_by_name[group_name]
            slots_by_name = {s.name: s for s in group.slots}
            for slot_data in slot_datas:
                slot = slots_by_name[slot_data["name"]]
                slot.assigned = slot_data["assigned"]

    def build_hotkey_dict(self) -> dict[str, Callable]:
        hk_dict = {}
        for group in self.hotkey_groups:
            for slot in group.slots:
                if not slot.enabled:
                    continue
                for hotkey in slot.assigned:
                    hk_dict[hotkey] = slot.slot
        return hk_dict
