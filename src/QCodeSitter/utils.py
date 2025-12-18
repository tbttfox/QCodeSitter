from typing import Union, Optional
from .constants import ENC
from Qt.QtCore import Qt
from Qt.QtGui import QKeySequence


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
        seqval |= int(mods)
    return QKeySequence(seqval).toString(QKeySequence.PortableText)


def dedent_string(indent: str, indent_using_tabs: bool, space_indent_width: int) -> str:
    """Remove one level of indentation from the indent string"""
    if indent_using_tabs:
        if indent.endswith("\t"):
            return indent[:-1]
    else:
        # Remove up to space_indent_width spaces from the end
        spaces_to_remove = min(space_indent_width, len(indent))
        # Count trailing spaces
        trailing_spaces = len(indent) - len(indent.rstrip(" "))
        actual_remove = min(spaces_to_remove, trailing_spaces)
        if actual_remove > 0:
            return indent[:-actual_remove]
    return indent


def len16(val: str):
    """Get the number of utf16 code points where surrogate pairs count as 2"""
    return len(val.encode(ENC)) // 2
