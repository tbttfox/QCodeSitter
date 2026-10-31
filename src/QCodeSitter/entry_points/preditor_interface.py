from __future__ import annotations

from functools import partial

import tree_sitter_python as tspython
from preditor.gui.workbox_mixin import WorkboxMixin
from Qt import QtCore, QtGui
from tree_sitter import Language

from ..behaviors.auto_bracket import AutoBracket  # noqa: F401
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
from ..hl_groups import (
    DARK_THEME,
    LIGHT_THEME,
    overlay_syntax,
    read_theme,
    resolve_capture,
)

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


# Maps a Qt property name to the (section, key) of the theme it overrides
# The section is "gui", "syntax", or "style"
THEME_PROPERTIES: dict[str, tuple[str, str]] = {}


def _themePropInit(name: str, section: str, key: str, default=None):
    """Initializes a theme property with a usable getter and setter.

    These properties are meant to be set from a stylesheet like
    `CodeSitterTextEdit { qproperty-hlKeyword: rgb(250, 24, 110); }`
    Color properties default to an invalid QColor, which means "use the built-in theme"
    """
    if default is None:
        default = QtGui.QColor()
    THEME_PROPERTIES[name] = (section, key)

    def _getattr(attrName, default, self):
        return self._theme_values.get(attrName, default)

    def _setattr(attrName, self, value):
        return self._set_theme_value(attrName, value)

    ga = partial(_getattr, name, default)
    sa = partial(_setattr, name)
    typ = default.__class__
    return QtCore.Property(typ, fget=(lambda s: ga(s)), fset=(lambda s, v: sa(s, v)))


def _colorToHex(color: QtGui.QColor) -> str:
    if color.alpha() == 255:
        return color.name(QtGui.QColor.NameFormat.HexRgb)
    return color.name(QtGui.QColor.NameFormat.HexArgb)


def _colorToCss(color: QtGui.QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


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
        # Stylesheets set the theme properties one at a time, so collect them all
        # and rebuild the theme once they're done
        self._theme_update_timer = QtCore.QTimer(self)
        self._theme_update_timer.setSingleShot(True)
        self._theme_update_timer.setInterval(0)
        self._theme_update_timer.timeout.connect(self.rebuildTheme)
        self._theme_values = {}

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

        self._windowStyleSheet = "Bright"
        window = self.window()
        if hasattr(window, "styleSheetChanged"):
            window.styleSheetChanged.connect(self.updateColorScheme)
        if hasattr(window, "_stylesheet"):
            self.updateColorScheme(window._stylesheet)

    def updateColorScheme(self, stylesheet):
        if stylesheet == self._windowStyleSheet:
            return
        self._windowStyleSheet = stylesheet
        self._theme_update_timer.start()

    def _baseTheme(self):
        """Pick the built-in theme that stylesheet properties are layered on top of"""
        bg = self._theme_values.get("guiBg")
        if bg is not None and bg.isValid():
            return DARK_THEME if bg.lightness() < 128 else LIGHT_THEME
        if str(self._windowStyleSheet).lower() == "dark":
            return DARK_THEME
        return LIGHT_THEME

    def buildTheme(self):
        """Build the gui colors and syntax specs from the built-in theme and any
        theme properties set by the stylesheet

        Returns:
            colors: The gui color dictionary
            syntax: The syntax spec dictionary
        """
        col, syn = read_theme(self._baseTheme())

        syn_colors = {}
        styles = {}
        for propName, value in self._theme_values.items():
            section, key = THEME_PROPERTIES[propName]
            if section == "style":
                styles[key] = set(value.replace(",", " ").split())
            elif value.isValid():
                if section == "gui":
                    col[key] = _colorToHex(value)
                else:
                    syn_colors[key] = {"color": _colorToHex(value)}

        syn = overlay_syntax(syn, syn_colors)

        # If the stylesheet defines the style lists, they take precedence
        for style, names in styles.items():
            lookup = {n: True for n in names}
            for name, spec in syn.items():
                spec[style] = resolve_capture(name, lookup) is not None

        return col, syn

    def rebuildTheme(self):
        col, syn = self.buildTheme()

        # The options are shared between editors, so only update them if they changed
        highlights = (HIGHLIGHT_QUERY, syn)
        if self.options.get("highlights") != highlights:
            self.options["highlights"] = highlights
        if self.options.get("colors") != col:
            self.options["colors"] = col

        # Make sure that preditor doesn't override the colors with its stylesheet
        bg = _colorToCss(QtGui.QColor(col["bg"]))
        fg = _colorToCss(QtGui.QColor(col["fg"]))
        sel = _colorToCss(QtGui.QColor(col.get("selection", col["bg"])))
        ss = (
            f"QWidget {{background-color: {bg};}}\n"
            f"QPlainTextEdit {{color: {fg}; selection-background-color: {sel};}}"
        )
        # Setting the stylesheet re-polishes the widget, which re-applies the
        # theme properties. Avoid doing that unless something actually changed
        if self.styleSheet() != ss:
            self.setStyleSheet(ss)

    def setText(self, text: str):
        """The WorkboxMixin assumes a QTextEdit, not a QPlainTextEdit
        So I have to reroute setText to setPlainText"""
        self.setPlainText(text)

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
                block = block.next()
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

    def _set_theme_value(self, attrName, value):
        if self._theme_values.get(attrName) == value:
            return
        self._theme_values[attrName] = value
        self._theme_update_timer.start()

    # fmt: off
    # GUI colors. See hl_groups.py for how these are used
    guiBg =              _themePropInit("guiBg",              "gui", "bg")
    guiBgDim =           _themePropInit("guiBgDim",           "gui", "bg_dim")
    guiFg =              _themePropInit("guiFg",              "gui", "fg")
    guiFgDim =           _themePropInit("guiFgDim",           "gui", "fg_dim")
    guiGutter =          _themePropInit("guiGutter",          "gui", "gutter")
    guiGutterFg =        _themePropInit("guiGutterFg",        "gui", "gutter_fg")
    guiHlDim =           _themePropInit("guiHlDim",           "gui", "hl_dim")
    guiMatchHl =         _themePropInit("guiMatchHl",         "gui", "match_hl")
    guiMenu =            _themePropInit("guiMenu",            "gui", "menu")
    guiOutsideBg =       _themePropInit("guiOutsideBg",       "gui", "outside_bg")
    guiPairHl =          _themePropInit("guiPairHl",          "gui", "pair_hl")
    guiPrimaryCursor =   _themePropInit("guiPrimaryCursor",   "gui", "primary_cursor")
    guiSecondaryCursor = _themePropInit("guiSecondaryCursor", "gui", "secondary_cursor")
    guiSelection =       _themePropInit("guiSelection",       "gui", "selection")
    guiSelectionColor =  _themePropInit("guiSelectionColor",  "gui", "selection_color")
    guiVisual =          _themePropInit("guiVisual",          "gui", "visual")

    # Syntax colors named after the treesitter captures. Unset captures fall back to
    # their parent group, so hlKeywordReturn falls back to hlKeyword
    hlAttribute =            _themePropInit("hlAttribute",            "syntax", "attribute")
    hlAttributeBuiltin =     _themePropInit("hlAttributeBuiltin",     "syntax", "attribute.builtin")
    hlBoolean =              _themePropInit("hlBoolean",              "syntax", "boolean")
    hlCharacterSpecial =     _themePropInit("hlCharacterSpecial",     "syntax", "character.special")
    hlComment =              _themePropInit("hlComment",              "syntax", "comment")
    hlConstant =             _themePropInit("hlConstant",             "syntax", "constant")
    hlConstantBuiltin =      _themePropInit("hlConstantBuiltin",      "syntax", "constant.builtin")
    hlConstructor =          _themePropInit("hlConstructor",          "syntax", "constructor")
    hlFunction =             _themePropInit("hlFunction",             "syntax", "function")
    hlFunctionBuiltin =      _themePropInit("hlFunctionBuiltin",      "syntax", "function.builtin")
    hlFunctionCall =         _themePropInit("hlFunctionCall",         "syntax", "function.call")
    hlFunctionMacro =        _themePropInit("hlFunctionMacro",        "syntax", "function.macro")
    hlFunctionMethod =       _themePropInit("hlFunctionMethod",       "syntax", "function.method")
    hlFunctionMethodCall =   _themePropInit("hlFunctionMethodCall",   "syntax", "function.method.call")
    hlKeyword =              _themePropInit("hlKeyword",              "syntax", "keyword")
    hlKeywordConditional =   _themePropInit("hlKeywordConditional",   "syntax", "keyword.conditional")
    hlKeywordCoroutine =     _themePropInit("hlKeywordCoroutine",     "syntax", "keyword.coroutine")
    hlKeywordDirective =     _themePropInit("hlKeywordDirective",     "syntax", "keyword.directive")
    hlKeywordException =     _themePropInit("hlKeywordException",     "syntax", "keyword.exception")
    hlKeywordFunction =      _themePropInit("hlKeywordFunction",      "syntax", "keyword.function")
    hlKeywordImport =        _themePropInit("hlKeywordImport",        "syntax", "keyword.import")
    hlKeywordOperator =      _themePropInit("hlKeywordOperator",      "syntax", "keyword.operator")
    hlKeywordRepeat =        _themePropInit("hlKeywordRepeat",        "syntax", "keyword.repeat")
    hlKeywordReturn =        _themePropInit("hlKeywordReturn",        "syntax", "keyword.return")
    hlKeywordType =          _themePropInit("hlKeywordType",          "syntax", "keyword.type")
    hlModule =               _themePropInit("hlModule",               "syntax", "module")
    hlModuleBuiltin =        _themePropInit("hlModuleBuiltin",        "syntax", "module.builtin")
    hlNone =                 _themePropInit("hlNone",                 "syntax", "none")
    hlNumber =               _themePropInit("hlNumber",               "syntax", "number")
    hlNumberFloat =          _themePropInit("hlNumberFloat",          "syntax", "number.float")
    hlOperator =             _themePropInit("hlOperator",             "syntax", "operator")
    hlPunctuation =          _themePropInit("hlPunctuation",          "syntax", "punctuation")
    hlPunctuationBracket =   _themePropInit("hlPunctuationBracket",   "syntax", "punctuation.bracket")
    hlPunctuationDelimiter = _themePropInit("hlPunctuationDelimiter", "syntax", "punctuation.delimiter")
    hlPunctuationSpecial =   _themePropInit("hlPunctuationSpecial",   "syntax", "punctuation.special")
    hlString =               _themePropInit("hlString",               "syntax", "string")
    hlStringDocumentation =  _themePropInit("hlStringDocumentation",  "syntax", "string.documentation")
    hlStringEscape =         _themePropInit("hlStringEscape",         "syntax", "string.escape")
    hlStringRegexp =         _themePropInit("hlStringRegexp",         "syntax", "string.regexp")
    hlType =                 _themePropInit("hlType",                 "syntax", "type")
    hlTypeBuiltin =          _themePropInit("hlTypeBuiltin",          "syntax", "type.builtin")
    hlTypeDefinition =       _themePropInit("hlTypeDefinition",       "syntax", "type.definition")
    hlVariable =             _themePropInit("hlVariable",             "syntax", "variable")
    hlVariableBuiltin =      _themePropInit("hlVariableBuiltin",      "syntax", "variable.builtin")
    hlVariableMember =       _themePropInit("hlVariableMember",       "syntax", "variable.member")
    hlVariableParameter =    _themePropInit("hlVariableParameter",    "syntax", "variable.parameter")

    # Space or comma separated lists of captures to draw italic or bold.
    # Like the colors, these apply to child captures as well
    hlItalic = _themePropInit("hlItalic", "style", "italic", "")
    hlBold =   _themePropInit("hlBold",   "style", "bold", "")
    # fmt: on
