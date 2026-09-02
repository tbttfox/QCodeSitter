from __future__ import annotations

from functools import partial

import tree_sitter_python as tspython
from preditor.gui.workbox_mixin import WorkboxMixin
from Qt import QtCore, QtGui
from tree_sitter import Language

from ..behaviors.auto_bracket import AutoBracket
from ..behaviors.code_folding import CodeFolding
from ..behaviors.comment_toggle import CommentToggle
from ..behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from ..behaviors.highlight_matching_selection import HighlightMatchingSelection
from ..behaviors.line_numbers import LineNumber
from ..behaviors.multi_cursor_paint import MultiCursorPaint
from ..behaviors.overscroll import Overscroll
from ..behaviors.providers.identifiers import IdentifierProvider
from ..behaviors.smart_indent import SmartIndent
from ..behaviors.syntax_highlighting import SyntaxHighlighting
from ..behaviors.tab_completion import TabCompletion
from ..code_editor import CodeEditor
from ..editor_options import EditorOptions
from ..highlight_query import HIGHLIGHT_QUERY
from ..hl_groups import DARK_THEME, LIGHT_THEME, read_theme

# ----------------------------------------------------------------------------------
# PrEditor colorscheme bridge
#
# PrEditor defines its editor colors through Qt stylesheet ``qproperty-*`` rules
# (see ``preditor/resource/stylesheet/*.css``).  ``CodeSitterTextEdit`` exposes a
# superset of those same Qt properties (built lower down by ``_colorPropInit``) so
# a PrEditor stylesheet can drive it too.  Any property the active stylesheet
# actually sets is treated as an override on top of the bundled dracula/edge
# themes from ``hl_groups`` - properties that are never set fall back to the
# bundled value, which keeps things working when no PrEditor stylesheet (or an
# older one without the richer rules) is present.
#
# ``_SYNTAX_PROP_MAP`` maps a Qt property name -> the tree-sitter capture groups
# it should recolor.  ``_GUI_PROP_MAP`` maps a Qt property name -> keys in the
# gui color palette (gutter, selection, cursor, ...).
# ----------------------------------------------------------------------------------

_SYNTAX_PROP_MAP: dict[str, tuple[str, ...]] = {
    # Names shared with PrEditor's existing DocumentEditor stylesheet block
    "colorDefault": ("none",),
    "colorComment": ("comment",),
    "colorCommentBlock": ("keyword.directive",),
    "colorNumber": ("number", "number.float"),
    "colorString": ("string", "string.regexp"),
    "colorTripleQuotedString": ("string.documentation",),
    "colorKeyword": (
        "keyword",
        "keyword.conditional",
        "keyword.coroutine",
        "keyword.exception",
        "keyword.function",
        "keyword.import",
        "keyword.operator",
        "keyword.repeat",
        "keyword.return",
        "keyword.type",
    ),
    "colorOperator": ("operator",),
    "colorMethod": ("function.method", "function.method.call"),
    "colorFunction": ("function", "function.call", "function.macro", "constructor"),
    "colorIdentifier": ("variable",),
    "colorDecorator": ("attribute", "attribute.builtin"),
    # Names new to the richer QCodeSitter scheme
    "colorBoolean": ("boolean",),
    "colorEscape": ("string.escape", "character.special"),
    "colorPunctuation": (
        "punctuation.bracket",
        "punctuation.delimiter",
        "punctuation.special",
    ),
    "colorFunctionBuiltin": ("function.builtin",),
    "colorMember": ("variable.member",),
    "colorParameter": ("variable.parameter",),
    "colorBuiltin": ("variable.builtin",),
    "colorConstant": ("constant", "constant.builtin"),
    "colorType": ("type", "type.definition"),
    "colorTypeBuiltin": ("type.builtin",),
    "colorModule": ("module", "module.builtin"),
}

_GUI_PROP_MAP: dict[str, tuple[str, ...]] = {
    "paperDefault": ("bg",),
    "pyMarginsBackgroundColor": ("gutter",),
    "pyMarginsForegroundColor": ("gutter_fg",),
    "pySelectionBackgroundColor": ("selection", "visual"),
    "pySelectionForegroundColor": ("selection_color",),
    "pyMatchedBraceBackgroundColor": ("pair_hl",),
    "pyCaretForegroundColor": ("primary_cursor",),
    "pyCaretBackgroundColor": ("secondary_cursor",),
    "colorSmartHighlight": ("match_hl",),
}


def _qcolor_to_hex(color: QtGui.QColor) -> str:
    """Return ``color`` as ``#RRGGBB`` (or ``#AARRGGBB`` when it has alpha)."""
    r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
    if a != 255:
        return f"#{a:02x}{r:02x}{g:02x}{b:02x}"
    return f"#{r:02x}{g:02x}{b:02x}"


_col, _syn = read_theme(LIGHT_THEME)
DEFAULT_OPTIONS = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
        "copy_indents_as_spaces": True,
        "language_name": "python",
        "language": Language(tspython.language()),
        "highlights": (HIGHLIGHT_QUERY, _syn),
        "colors": _col,
        "font": QtGui.QFont("MS Shell Dlg 2", pointSize=11),
        "vim_completion_keys": True,  # c-n c-p for next/prev  c-y for accept
        "debounce_delay": 150,  # in milliseconds
        "auto_bracket_enabled": True,
        "auto_bracket_pairs": "()[]{}\"\"''``",
        "indent_bracket_pairs": ["()", "[]", "{}"],
        "highlight_bracket_pairs": ["()", "[]", "{}"],
        "highlight_quote_pairs": "\"'`",
    }
)


def _colorPropInit(name: str, default):
    """Initializes a default color property value with a usable getter and setter."""

    def _getattr(attrName, default, self):
        return self._color_property(attrName, default)

    def _setattr(attrName, self, value):
        return self._set_color_property(attrName, value)

    ga = partial(_getattr, name, default)
    sa = partial(_setattr, name)
    typ = default.__class__
    return QtCore.Property(typ, fget=(lambda s: ga(s)), fset=(lambda s, v: sa(s, v)))


class CodeSitterTextEdit(WorkboxMixin, CodeEditor):
    """A full-featured multi-cursor editor powered by treesitter"""

    def __init__(
        self,
        console=None,
        core_name=None,
        delayable_engine="default",
        parent=None,
        **kwargs,
    ):
        self.options = DEFAULT_OPTIONS
        super().__init__(
            parent=parent,
            console=console,
            core_name=core_name,
            delayable_engine=delayable_engine,
            options=self.options,
            **kwargs,
        )
        self._color_upate_timer = QtCore.QTimer()
        self._color_upate_timer.setSingleShot(True)
        self._color_upate_timer.setInterval(0)
        self._color_upate_timer.timeout.connect(self._color_properties_updated)
        # Qt property values that a PrEditor stylesheet has explicitly set. Only
        # keys present here override the bundled theme.
        self._color_prop_values: dict[str, QtGui.QColor] = {}
        self._color_tracker: set[str] = set()
        self._windowStyleSheet = "Bright"
        self._style_signal_connected = False
        self._applied_bg_ss = None

        self._encoding = None
        self.__set_console__(console)

        _old, cmp_bh = self.addBehavior(TabCompletion)
        cmp_bh.addProvider(IdentifierProvider)

        self.addBehavior(SyntaxHighlighting)
        self.addBehavior(SmartIndent)
        self.addBehavior(HighlightMatchingBrackets)
        self.addBehavior(HighlightMatchingSelection)
        self.addBehavior(LineNumber)
        self.addBehavior(Overscroll)
        self.addBehavior(MultiCursorPaint)
        # self.addBehavior(AutoBracket)
        self.addBehavior(CodeFolding)
        self.addBehavior(CommentToggle)

        self._ensure_style_connection()

    def _ensure_style_connection(self):
        """Hook up to the PrEditor window's ``styleSheetChanged`` signal.

        Safe to call more than once; the connection is only made once and only
        when a PrEditor-style window is actually reachable.
        """
        window = self.window()
        if window is None:
            return
        if not self._style_signal_connected and hasattr(window, "styleSheetChanged"):
            window.styleSheetChanged.connect(self.updateColorScheme)
            self._style_signal_connected = True
        stylesheet = getattr(window, "_stylesheet", None)
        if stylesheet:
            self.updateColorScheme(stylesheet)

    def updateColorScheme(self, stylesheet=None):
        """Slot for PrEditor's ``styleSheetChanged(str)`` signal.

        ``stylesheet`` is the name (or css text) of the newly applied window
        stylesheet. We only use it to decide between the light and dark bundled
        themes - the fine grained colors come from the Qt ``qproperty-*`` values
        the stylesheet sets on this widget (see ``_apply_theme``).
        """
        if stylesheet:
            self._windowStyleSheet = stylesheet
        self._apply_theme()

    def _color_properties_updated(self):
        """Debounced handler: a stylesheet has changed one or more color props."""
        self._apply_theme()

    def _apply_theme(self):
        """Rebuild the editor color options from the bundled theme + overrides."""
        dark = "dark" in (self._windowStyleSheet or "").lower()
        base = DARK_THEME if dark else LIGHT_THEME
        col, syn = read_theme(base)

        for prop, qcolor in self._color_prop_values.items():
            hexcol = _qcolor_to_hex(qcolor)
            for group in _SYNTAX_PROP_MAP.get(prop, ()):
                spec = dict(syn.get(group, {}))
                spec["color"] = hexcol
                syn[group] = spec
            for key in _GUI_PROP_MAP.get(prop, ()):
                col[key] = hexcol

        self._color_tracker = set()

        self.options["highlights"] = (HIGHLIGHT_QUERY, syn)
        self.options["colors"] = col

        # Make sure that preditor doesn't override the bg color
        # with its window stylesheet.
        bgcolor = QtGui.QColor(col["bg"])
        bgc = (bgcolor.red(), bgcolor.green(), bgcolor.blue())
        ss = f"QWidget {{background-color: rgb{bgc}}}"
        if ss != self._applied_bg_ss:
            self._applied_bg_ss = ss
            self.setStyleSheet(ss)

    def _color_property(self, name, default):
        values = self.__dict__.get("_color_prop_values")
        if not values or name not in values:
            return default
        return values[name]

    def _set_color_property(self, name, value):
        values = self.__dict__.setdefault("_color_prop_values", {})
        if values.get(name) == value:
            # No change - bail out so re-polishing the stylesheet (which we can
            # trigger ourselves via setStyleSheet) can't cause an update loop.
            return
        values[name] = value
        self.__dict__.setdefault("_color_tracker", set()).add(name)
        timer = self.__dict__.get("_color_upate_timer")
        if timer is not None:
            timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        # The window stylesheet is usually fully polished by the time we're
        # shown, so this is the reliable place to pick up PrEditor's colors.
        self._ensure_style_connection()
        self._apply_theme()

    def setText(self, text: str):
        """The WorkboxMixin assumes a QTextEdit, not a QPlainTextEdit
        So I have to reroute setText to setPlainText"""
        self.setPlainText(text)
        self.tree_manager.fullUpdate()

    def __num_lines__(self):
        return self.document().blockCount()

    def __text_part__(self, lineNum=None, start=None, end=None):
        doc = self.document()
        if lineNum is not None:
            block = doc.findBlockByNumber(lineNum)
            return block.text()
        if start is not None and end is not None:
            block = doc.findBlockByNumber(start)
            lines = []
            for _ in range(start, end):
                lines.append(block.text())
                block.next()
                if not block.isValid():
                    break
            return "\n".join(lines)
        if start is None and end is None:
            return self.__text__()

        raise ValueError("You must pass start and end if you pass either.")

    def __auto_complete_enabled__(self):
        bh = self.getBehavior(TabCompletion)
        return bh is not None

    def __set_auto_complete_enabled__(self, state: bool):
        if state == self.__auto_complete_enabled__():
            return
        if state:
            _old, cmp_bh = self.addBehavior(TabCompletion)
            cmp_bh.addProvider(IdentifierProvider)
        else:
            self.removeBehavior(TabCompletion)

    def __clear__(self):
        self.clear()
        self.__set_last_saved_text__(self.__text__())

    def __copy_indents_as_spaces__(self):
        """When copying code, should it convert leading tabs to spaces?"""
        return self.options["copy_indents_as_spaces"]

    def __set_copy_indents_as_spaces__(self, state: bool):
        self.options["copy_indents_as_spaces"] = state

    def __cursor_position__(self):
        """Returns the line and index of the cursor."""
        cursor = self.textCursor()
        sc = QtGui.QTextCursor(self.document())
        sc.setPosition(cursor.selectionStart())
        return sc.blockNumber(), sc.positionInBlock()

    def __font__(self):
        return self.options["font"]

    def __set_font__(self, font: QtGui.QFont):
        self.options["font"] = font

    def __goto_line__(self, line):
        self.exit_multi_cursor_mode()
        cursor = QtGui.QTextCursor(self.document().findBlockByNumber(line - 1))
        self.setTextCursor(cursor)

    def __indentations_use_tabs__(self):
        return self.options["indent_using_tabs"]

    def __set_indentations_use_tabs__(self, state: bool):
        self.options["indent_using_tabs"] = state

    def __margins_font__(self):
        return QtGui.QFont()

    def __set_margins_font__(self, font):
        pass

    def __tab_width__(self):
        return self.options["space_indent_width"]

    def __text__(self):
        """Returns the text in this widget
        Returns:
            str: Returns the text in this widget
        """
        return self.toPlainText()

    def __selected_text__(self, start_of_line=False, selectText=False):
        cursor = self.textCursor()

        # Get starting line number. Must set the cursor's position to the start of the
        # selection, otherwise we may instead get the ending line number.
        tempCursor = self.textCursor()
        tempCursor.setPosition(tempCursor.selectionStart())
        line = tempCursor.block().firstLineNumber()

        # If no selection, return the current line
        if cursor.selection().isEmpty():
            text = cursor.block().text()

            if selectText:
                cursor.select(QtGui.QTextCursor.SelectionType.LineUnderCursor)
                self.setTextCursor(cursor)

            return text, line

        # Otherwise return the selected text
        if start_of_line:
            sc = QtGui.QTextCursor(self.document())
            sc.setPosition(cursor.selectionStart())
            sc.movePosition(cursor.StartOfLine, sc.MoveAnchor)
            sc.setPosition(cursor.selectionEnd(), sc.KeepAnchor)

            return sc.selection().toPlainText(), line

        return self.textCursor().selection().toPlainText(), line

    def keyPressEvent(self, event):
        if self.process_shortcut(event):
            return
        else:
            super().keyPressEvent(event)

    # fmt: off
    paperDefault = _colorPropInit("paperDefault", QtGui.QColor(255, 255, 255))
    pyMarginsForegroundColor = _colorPropInit("pyMarginsForegroundColor", QtGui.QColor(202, 202, 202))
    pyMarginsBackgroundColor = _colorPropInit("pyMarginsBackgroundColor", QtGui.QColor(70, 70, 73))
    pySelectionBackgroundColor = _colorPropInit("pySelectionBackgroundColor", QtGui.QColor(90, 90, 93))
    pySelectionForegroundColor = _colorPropInit("pySelectionForegroundColor", QtGui.QColor(240, 240, 240))
    pyCaretBackgroundColor = _colorPropInit("pyCaretBackgroundColor", QtGui.QColor(70, 70, 73))
    pyCaretForegroundColor = _colorPropInit("pyCaretForegroundColor", QtGui.QColor(255, 255, 255))
    pyMatchedBraceBackgroundColor = _colorPropInit("pyMatchedBraceBackgroundColor", QtGui.QColor(60, 60, 63))
    pyMatchedBraceForegroundColor = _colorPropInit("pyMatchedBraceForegroundColor", QtGui.QColor(240, 240, 240))
    pyUnmatchedBraceBackgroundColor = _colorPropInit("pyUnmatchedBraceBackgroundColor", QtGui.QColor(70, 70, 73))
    pyUnmatchedBraceForegroundColor = _colorPropInit("pyUnmatchedBraceForegroundColor", QtGui.QColor(200, 180, 180))
    pyEdgeColor = _colorPropInit("pyEdgeColor", QtGui.QColor(100, 45, 45))

    pyIndentationGuidesBackgroundColor = _colorPropInit("pyIndentationGuidesBackgroundColor", QtGui.QColor(70, 70, 73))
    pyIndentationGuidesForegroundColor = _colorPropInit("pyIndentationGuidesForegroundColor", QtGui.QColor(102, 153, 204))
    pyMarkerBackgroundColor = _colorPropInit("pyMarkerBackgroundColor", QtGui.QColor(45, 255, 45))
    pyMarkerForegroundColor = _colorPropInit("pyMarkerForegroundColor", QtGui.QColor(200, 0, 200))
    foldMarginsBackgroundColor = _colorPropInit("foldMarginsBackgroundColor", QtGui.QColor(60, 60, 63))
    foldMarginsForegroundColor = _colorPropInit("foldMarginsForegroundColor", QtGui.QColor(60, 60, 63))
    braceBadForeground = _colorPropInit("braceBadForeground", QtGui.QColor(255, 255, 255))
    braceBadBackground = _colorPropInit("braceBadBackground", QtGui.QColor(100, 60, 60))

    colorDefault = _colorPropInit("colorDefault", QtGui.QColor(22, 160, 250))
    colorComment = _colorPropInit("colorComment", QtGui.QColor(0, 160, 0))
    colorNumber = _colorPropInit("colorNumber", QtGui.QColor(0, 200, 200))
    colorString = _colorPropInit("colorString", QtGui.QColor(240, 135, 0))
    colorKeyword = _colorPropInit("colorKeyword", QtGui.QColor(250, 24, 110))
    colorTripleQuotedString = _colorPropInit("colorTripleQuotedString", QtGui.QColor(240, 135, 0))
    colorMethod = _colorPropInit("colorMethod", QtGui.QColor(255, 204, 102))
    colorFunction = _colorPropInit("colorFunction", QtGui.QColor(22, 160, 250))
    colorOperator = _colorPropInit("colorOperator", QtGui.QColor(204, 204, 204))
    colorIdentifier = _colorPropInit("colorIdentifier", QtGui.QColor(22, 160, 250))
    colorCommentBlock = _colorPropInit("colorCommentBlock", QtGui.QColor(117, 113, 94))
    colorUnclosedString = _colorPropInit("colorUnclosedString", QtGui.QColor(255, 255, 255))
    colorSmartHighlight = _colorPropInit("colorSmartHighlight", QtGui.QColor(255, 255, 255))
    colorDecorator = _colorPropInit("colorDecorator", QtGui.QColor(240, 100, 102))

    # Richer tree-sitter aware groups (new to QCodeSitter, ignored by QScintilla)
    colorBoolean = _colorPropInit("colorBoolean", QtGui.QColor(80, 250, 123))
    colorEscape = _colorPropInit("colorEscape", QtGui.QColor(139, 233, 253))
    colorPunctuation = _colorPropInit("colorPunctuation", QtGui.QColor(248, 248, 242))
    colorFunctionBuiltin = _colorPropInit("colorFunctionBuiltin", QtGui.QColor(139, 233, 253))
    colorMember = _colorPropInit("colorMember", QtGui.QColor(255, 184, 108))
    colorParameter = _colorPropInit("colorParameter", QtGui.QColor(255, 184, 108))
    colorBuiltin = _colorPropInit("colorBuiltin", QtGui.QColor(189, 147, 249))
    colorConstant = _colorPropInit("colorConstant", QtGui.QColor(189, 147, 249))
    colorType = _colorPropInit("colorType", QtGui.QColor(164, 255, 255))
    colorTypeBuiltin = _colorPropInit("colorTypeBuiltin", QtGui.QColor(139, 233, 253))
    colorModule = _colorPropInit("colorModule", QtGui.QColor(255, 184, 108))
    # fmt: on
