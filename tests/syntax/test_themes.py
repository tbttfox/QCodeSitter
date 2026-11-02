"""Tests for the color themes and gui colors"""

from __future__ import annotations

import pytest
from Qt import QtGui

from QCodeSitter.gui_colors import DERIVED_GUI_COLORS, GUI_COLOR_DEFAULTS, gui_color
from QCodeSitter.highlighting.themes import (
    DARK_THEME,
    LIGHT_THEME,
    overlay_syntax,
    read_theme,
    resolve_capture,
)


class TestThemes:
    def test_read_theme_resolves_palette(self):
        colors, syntax = read_theme(
            {
                "palette": {"red": "#FF0000"},
                "gui": {"bg": "red", "fg": "#FFFFFF"},
                "syntax": {
                    "keyword": {"color": "red", "bold": True},
                    "plain": {"italic": True},
                },
            }
        )
        assert colors == {"bg": "#FF0000", "fg": "#FFFFFF", "red": "#FF0000"}
        assert syntax == {
            "keyword": {"color": "#FF0000", "bold": True},
            "plain": {"italic": True},
        }

    def test_read_theme_gui_wins_over_palette(self):
        colors, syntax = read_theme(
            {
                "palette": {"bg": "#000000", "accent": "#00FF00"},
                "gui": {"bg": "#FFFFFF"},
                "syntax": {"keyword": {"color": "bg"}},
            }
        )
        assert colors == {"bg": "#FFFFFF", "accent": "#00FF00"}
        assert syntax == {"keyword": {"color": "#FFFFFF"}}

    def test_read_theme_warns_about_unknown_names(self, qapp):
        theme = {"palette": {"red": "#FF0000"}, "gui": {"bg": "rde"}, "syntax": {}}
        with pytest.warns(UserWarning, match="gui 'bg' color 'rde'"):
            colors, _syntax = read_theme(theme)
        assert colors["bg"] == "rde"

    @pytest.mark.parametrize("theme", [DARK_THEME, LIGHT_THEME])
    def test_built_in_themes_resolve(self, qapp, recwarn, theme):
        colors, syntax = read_theme(theme)
        assert not recwarn.list
        # Every gui color in a theme is one the editor uses
        assert set(theme["gui"]) <= set(GUI_COLOR_DEFAULTS) | set(DERIVED_GUI_COLORS)
        for name in [*GUI_COLOR_DEFAULTS, *DERIVED_GUI_COLORS]:
            assert gui_color(colors, name).isValid(), name
        assert all(QtGui.QColor(spec["color"]).isValid() for spec in syntax.values())

    def test_resolve_capture(self):
        specs = {"function": 1, "function.method": 2}
        assert resolve_capture("function.method.call", specs) == 2
        assert resolve_capture("function.builtin", specs) == 1
        assert resolve_capture("keyword", specs) is None

    def test_overlay_syntax(self):
        base = {"keyword": {"color": "a"}, "keyword.return": {"color": "b"}}
        out = overlay_syntax(base, {"keyword": {"color": "c"}})
        assert out == {"keyword": {"color": "c"}, "keyword.return": {"color": "c"}}

    def test_gui_color_default(self, qapp):
        assert gui_color({}, "pair_hl") == QtGui.QColor(GUI_COLOR_DEFAULTS["pair_hl"])
        assert gui_color({"pair_hl": "#010203"}, "pair_hl") == QtGui.QColor("#010203")

    def test_derived_gui_color_default(self, qapp):
        darker = QtGui.QColor("#646464").darker(120)
        assert gui_color({"bg": "#646464"}, "outside_bg") == darker
        assert gui_color({"outside_bg": "#010203"}, "outside_bg") == QtGui.QColor(
            "#010203"
        )
