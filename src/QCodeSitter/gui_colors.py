"""The "colors" option: named colors for the editor chrome and the behaviors

Every color the editor and the built-in behaviors use has a default in
GUI_COLOR_DEFAULTS, or in DERIVED_GUI_COLORS when it depends on another color.
`gui_color` falls back to them for any color a theme doesn't set.

Hex colors with alpha should be given in ARGB order, which is how QColor reads them.
"""

from __future__ import annotations

from collections.abc import Callable

from Qt import QtGui

# Gui color name -> hex color
GuiColors = dict[str, str]

GUI_COLOR_DEFAULTS: GuiColors = {
    "bg": "#282828",
    "fg": "#DCDCDC",
    "gutter": "#282828",
    "gutter_fg": "#969696",
    "bg_dim": "#503C3C3C",
    "fg_dim": "#C8787878",
    "hl_dim": "#96464646",
    "manual_fold": "#D7BA7D",
    "match_hl": "#50FFFF00",
    "menu": "#2B2B2B",
    "pair_hl": "#C8C8C8",
    "primary_cursor": "#FFFFFFFF",
    "secondary_cursor": "#B4B4B4",
    "selection": "#094771",
    "secondary_selection": "#264F78",
}

# Gui color name -> its default, made from the other colors
DERIVED_GUI_COLORS: dict[str, Callable[[GuiColors], QtGui.QColor]] = {
    # The space below the document is a shade darker than the background
    "outside_bg": lambda colors: gui_color(colors, "bg").darker(120),
}


def gui_color(colors: GuiColors, name: str) -> QtGui.QColor:
    """Get a gui color, falling back to its default if the theme doesn't set it"""
    if name in colors:
        return QtGui.QColor(colors[name])
    derive = DERIVED_GUI_COLORS.get(name)
    if derive is not None:
        return derive(colors)
    return QtGui.QColor(GUI_COLOR_DEFAULTS[name])
