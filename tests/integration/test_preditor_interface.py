"""Tests for the PrEditor workbox plugin"""

from __future__ import annotations

import pytest
from Qt import QtGui, QtWidgets

pytest.importorskip("preditor")

from QCodeSitter.behaviors.tab_completion import TabCompletion
from QCodeSitter.gui_colors import DERIVED_GUI_COLORS, GUI_COLOR_DEFAULTS
from QCodeSitter.integrations.preditor_interface import (
    CodeSitterTextEdit,
)
from QCodeSitter.themes import DARK_THEME, LIGHT_THEME, read_theme
from tests.helpers import (
    assert_tree_matches_fresh_parse,
    menu_actions,
    set_cursor_selection,
)

TEXT = "first line\n    second line\nthird line\n"


class _TabBar(QtWidgets.QTabBar):
    """The parts of PrEditor's tab bar that a workbox connects to"""

    def updateColorsAndToolTips(self, *_args):
        pass


class _TabWidget(QtWidgets.QTabWidget):
    def __init__(self):
        super().__init__()
        self.setTabBar(_TabBar())


@pytest.fixture
def tabs(qtbot):
    widget = _TabWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def workbox(qtbot, tabs):
    # Giving it an id stops PrEditor from making a backup file for it
    box = CodeSitterTextEdit(parent=tabs, workbox_id="qcodesitter_test")
    tabs.addTab(box, "test")
    tabs.show()
    qtbot.waitExposed(tabs)
    box.setText(TEXT)
    return box


class TestWorkboxText:
    def test_text(self, workbox):
        assert workbox.__text__() == TEXT
        assert workbox.__num_lines__() == 4

    def test_text_part(self, workbox):
        assert workbox.__text_part__(lineNum=1) == "    second line"
        # start and end are character offsets, like PrEditor's selection offsets
        assert workbox.__text_part__(start=6, end=15) == "line\n    "
        assert workbox.__text_part__() == TEXT
        with pytest.raises(ValueError):
            workbox.__text_part__(start=1)

    def test_selected_text(self, workbox):
        # Without a selection, it's the cursor's line
        set_cursor_selection(workbox, 15, 15)
        assert workbox.__selected_text__() == ("    second line", 1)

        set_cursor_selection(workbox, 15, 21)
        assert workbox.__selected_text__() == ("second", 1)
        assert workbox.__selected_text__(start_of_line=True) == ("    second", 1)

    def test_selected_text_line_counts_wrapped_lines_once(self, workbox):
        long_line = "word " * 200
        workbox.setText(long_line + "\nnext")
        # Laying out the long line wraps it, so the next block starts on a later line
        workbox.blockBoundingRect(workbox.document().firstBlock())
        assert workbox.document().findBlockByNumber(1).firstLineNumber() > 1
        set_cursor_selection(workbox, len(long_line) + 1, len(long_line) + 1)
        assert workbox.__selected_text__() == ("next", 1)

    def test_cursor_position_and_goto(self, workbox):
        workbox.__goto_line__(3)
        assert workbox.__cursor_position__() == (2, 0)

    def test_clear(self, workbox):
        workbox.__clear__()
        assert workbox.__text__() == ""
        assert_tree_matches_fresh_parse(workbox)

    def test_set_cursor_position(self, workbox):
        workbox.__set_cursor_position__(1, 4)
        assert workbox.__cursor_position__() == (1, 4)
        # An index past the end of the line stops at its end
        workbox.__set_cursor_position__(0, 99)
        assert workbox.__cursor_position__() == (0, len("first line"))

    @pytest.mark.parametrize(
        ("line", "index", "expected"),
        [(-5, -3, (0, 0)), (99, 0, (3, 0)), (2, -1, (2, 0))],
    )
    def test_set_cursor_position_clamps(self, workbox, line, index, expected):
        workbox.__set_cursor_position__(line, index)
        assert workbox.__cursor_position__() == expected

    @pytest.mark.parametrize(("line", "expected"), [(0, (0, 0)), (99, (3, 0))])
    def test_goto_line_clamps(self, workbox, line, expected):
        """Lines are 1-based, and out of range lines stop at the first or last"""
        set_cursor_selection(workbox, 15, 15)
        workbox.__goto_line__(line)
        assert workbox.__cursor_position__() == expected

    def test_replace_selection_like_logger_window(self, workbox):
        """LoggerWindow removes the selection, inserts text, then moves past it"""
        set_cursor_selection(workbox, 0, 5)
        workbox.__remove_selected_text__()
        workbox.__insert_text__("last")
        line, index = workbox.__cursor_position__()
        workbox.__set_cursor_position__(line, index)
        assert workbox.__text__().startswith("last line\n")
        assert workbox.__cursor_position__() == (0, 4)
        assert_tree_matches_fresh_parse(workbox)

    def test_populate_edit_menu(self, workbox):
        """LoggerWindow's Workbox menu comes from __populate_edit_menu__"""
        menu = QtWidgets.QMenu()
        set_cursor_selection(workbox, 0, 0)
        workbox.__populate_edit_menu__(menu)
        actions = menu_actions(menu)
        assert "Multi-Cursor/Add Next Occurrence" in actions
        actions["Toggle Comment"].trigger()
        assert workbox.__text_part__(lineNum=0) == "# first line"

    def test_edit_menu_shortcuts_are_not_bound(self, workbox):
        """The window's menu must not take the keys when the workbox isn't focused"""
        menu = QtWidgets.QMenu()
        workbox.__populate_edit_menu__(menu)
        assert all(a.shortcut().isEmpty() for a in menu_actions(menu).values())


class TestWorkboxSettings:
    def test_options_are_per_editor(self, tabs, workbox):
        """Changing one workbox's settings doesn't change another's"""
        other = CodeSitterTextEdit(parent=tabs, workbox_id="qcodesitter_other")
        tabs.addTab(other, "other")
        workbox.__set_indentations_use_tabs__(True)
        workbox.__set_font__(QtGui.QFont("Courier", 20))
        assert workbox.__indentations_use_tabs__()
        assert not other.__indentations_use_tabs__()
        assert other.__font__().pointSize() != 20
        assert workbox.options is not other.options

    def test_copy_indents_as_spaces(self, workbox):
        workbox.__set_copy_indents_as_spaces__(False)
        assert workbox.__copy_indents_as_spaces__() is False
        assert workbox.options["copy_indents_as_spaces"] is False

    def test_tab_width(self, workbox):
        assert workbox.__tab_width__() == 4
        workbox.__set_tab_width__(2)
        assert workbox.__tab_width__() == 2
        assert workbox.options["space_indent_width"] == 2

    def test_margins_font_is_the_editor_font(self, workbox):
        font = QtGui.QFont("Courier", 17)
        workbox.__set_font__(font)
        assert workbox.__margins_font__() == font

    def test_auto_complete_toggle(self, workbox):
        assert workbox.__auto_complete_enabled__()
        workbox.__set_auto_complete_enabled__(False)
        assert workbox.get_behavior(TabCompletion) is None
        workbox.__set_auto_complete_enabled__(True)
        assert workbox.get_behavior(TabCompletion) is not None

    def test_auto_complete_toggle_removes_a_subclass(self, workbox):
        class MyCompletion(TabCompletion):
            pass

        workbox.remove_behavior(TabCompletion)
        workbox.add_behavior(MyCompletion)
        workbox.__set_auto_complete_enabled__(False)
        assert workbox.get_behavior(TabCompletion) is None


class TestTheme:
    def test_gui_properties_match_the_gui_colors(self):
        """There is a gui property for each gui color, and no others"""
        meta = CodeSitterTextEdit.staticMetaObject
        names = {
            meta.property(i).name()
            for i in range(meta.propertyOffset(), meta.propertyCount())
        }
        gui = {name for name in names if name.startswith("gui")}
        expected = {
            "gui" + "".join(part.title() for part in color.split("_"))
            for color in {*GUI_COLOR_DEFAULTS, *DERIVED_GUI_COLORS}
        }
        assert gui == expected

    @pytest.mark.parametrize("name", ["guiBg", "hlKeyword", "hlItalic"])
    def test_theme_properties_are_qt_properties(self, name):
        """Stylesheets can only set properties Qt knows about"""
        meta = CodeSitterTextEdit.staticMetaObject
        assert meta.indexOfProperty(name) >= 0

    def test_property_setter_round_trip(self, workbox):
        workbox.setProperty("hlString", QtGui.QColor("#00ff00"))
        assert workbox.hlString == QtGui.QColor("#00ff00")

    def test_default_theme_is_light(self, workbox):
        colors, syntax = workbox.build_theme()
        assert (colors, syntax) == read_theme(LIGHT_THEME)

    def test_dark_stylesheet(self, workbox):
        workbox.update_color_scheme("Dark")
        assert workbox.build_theme() == read_theme(DARK_THEME)

    def test_gui_property_overrides_color(self, workbox):
        workbox.guiFg = QtGui.QColor("#123456")
        colors, _syntax = workbox.build_theme()
        assert colors["fg"] == "#123456"

    def test_dark_background_picks_dark_theme(self, workbox):
        workbox.guiBg = QtGui.QColor("#000000")
        _colors, syntax = workbox.build_theme()
        assert syntax["keyword"] == read_theme(DARK_THEME)[1]["keyword"]

    def test_syntax_property_overrides_children(self, workbox):
        """An override for a group applies to its child captures"""
        workbox.hlKeyword = QtGui.QColor("#ff0000")
        _colors, syntax = workbox.build_theme()
        assert syntax["keyword"]["color"] == "#ff0000"
        assert syntax["keyword.return"]["color"] == "#ff0000"

    def test_style_lists(self, workbox):
        workbox.hlItalic = "comment, keyword"
        _colors, syntax = workbox.build_theme()
        assert syntax["comment"]["italic"] is True
        assert syntax["keyword.return"]["italic"] is True
        assert syntax["string"]["italic"] is False

    def test_parent_stylesheet_applies_on_creation(self, qtbot, tabs):
        """Theme properties a stylesheet sets while the widget is built are kept"""
        tabs.setStyleSheet(
            "CodeSitterTextEdit { qproperty-hlKeyword: rgb(255, 0, 0); }"
        )
        box = CodeSitterTextEdit(parent=tabs, workbox_id="qcodesitter_styled")
        tabs.addTab(box, "styled")
        tabs.show()
        qtbot.waitExposed(tabs)
        qtbot.waitUntil(lambda: box.options["syntax"]["keyword"]["color"] == "#ff0000")

    def test_rebuild_theme_updates_options(self, qtbot, workbox):
        workbox.guiBg = QtGui.QColor("#101010")
        qtbot.waitUntil(lambda: workbox.options["colors"]["bg"] == "#101010")
        assert "#101010" not in workbox.styleSheet()
        assert "rgba(16, 16, 16, 255)" in workbox.styleSheet()
