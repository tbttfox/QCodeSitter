"""Utilities for intrinsic keymaps (not user-configurable shortcuts).

This module provides the `hk` function for building hashable hotkey strings
used by intrinsic editing behaviors like Tab, Return, Backspace, etc.

For user-configurable shortcuts, use QtShortcutManager instead.
"""

from __future__ import annotations
from typing import Union, Optional
from Qt.QtCore import Qt
from Qt.QtGui import QKeySequence
from Qt import QtCompat


def hk(
    key: Union[Qt.Key, int],
    mods: Optional[Union[Qt.KeyboardModifier, Qt.KeyboardModifiers, int]] = None,
) -> str:
    """Build a hashable hotkey string for intrinsic keymaps.

    This function converts Qt key events into portable string representations
    that can be used as dictionary keys for intrinsic editing behaviors.

    Args:
        key: The Qt key code (e.g., Qt.Key.Key_Tab, Qt.Key.Key_Return)
        mods: Optional keyboard modifiers (e.g., Qt.KeyboardModifier.ShiftModifier)

    Returns:
        A portable string representation (e.g., "Tab", "Shift+Tab", "Return")

    Example:
        >>> hk(Qt.Key.Key_Tab)
        'Tab'
        >>> hk(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        'Shift+Tab'

    Note:
        This is for INTRINSIC keymaps only (like Tab, Return, Backspace).
        For user-configurable shortcuts, use QtShortcutManager's ShortcutSlot.
    """
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
