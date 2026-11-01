"""The "colors" option: named colors for the editor chrome and the behaviors

Every color the editor and the built-in behaviors use is listed in
GUI_COLOR_DEFAULTS, and `gui_color` falls back to it for any color a theme
doesn't set. "outside_bg" is the exception: it defaults to a darkened "bg".

Hex colors with alpha should be given in ARGB order, which is how QColor reads them.
"""

from __future__ import annotations

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
    "match_hl": "#50FFFF00",
    "menu": "#2B2B2B",
    "pair_hl": "#C8C8C8",
    "primary_cursor": "#FFFFFFFF",
    "secondary_cursor": "#B4B4B4",
    "selection": "#094771",
    "secondary_selection": "#B4B4B4",
}


def gui_color(colors: GuiColors, name: str) -> QtGui.QColor:
    """Get a gui color, falling back to its default if the theme doesn't set it"""
    return QtGui.QColor(colors.get(name, GUI_COLOR_DEFAULTS[name]))
