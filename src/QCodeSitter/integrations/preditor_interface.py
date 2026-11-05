from __future__ import annotations

from typing import Literal

from preditor.gui.workbox_mixin import WorkboxMixin
from Qt import QtCore, QtGui, QtWidgets

from .. import CodeEditor
from ..behaviors.tab_completion import TabCompletion
from ..defaults import (
    default_options,
    install_default_behaviors,
    install_tab_completion,
)
from ..gui_colors import GuiColors, gui_color
from ..syntax_specs import SyntaxSpecs, overlay_syntax, resolve_capture
from ..themes import DARK_THEME, LIGHT_THEME, Theme, read_theme
from ..utils import MM, MO

ThemeSection = Literal["gui", "syntax", "style"]
# A theme value is identified by its section and key
ThemeKey = tuple[ThemeSection, str]
# Colors for the "gui" and "syntax" sections, and capture name lists for "style"
ThemeValue = QtGui.QColor | str


def _theme_property(
    section: ThemeSection, key: str, default: ThemeValue | None = None
) -> QtCore.Property:
    """Make a Qt property that overrides one value of the theme

    These properties are meant to be set from a stylesheet like
    `CodeSitterTextEdit { qproperty-hlKeyword: rgb(250, 24, 110); }`
    Color properties default to an invalid QColor, which means "use the built-in theme"
    """
    if default is None:
        default = QtGui.QColor()

    def fget(self: CodeSitterTextEdit) -> ThemeValue:
        return self._theme_values.get((section, key), default)

    def fset(self: CodeSitterTextEdit, value: ThemeValue) -> None:
        self._set_theme_value((section, key), value)

    return QtCore.Property(type(default), fget=fget, fset=fset)


def _color_to_hex(color: QtGui.QColor) -> str:
    if color.alpha() == 255:
        return color.name(QtGui.QColor.NameFormat.HexRgb)
    return color.name(QtGui.QColor.NameFormat.HexArgb)


def _color_to_css(color: QtGui.QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


class CodeSitterTextEdit(WorkboxMixin, CodeEditor):
    """A full-featured multi-cursor editor powered by treesitter"""

    def __init__(
        self,
        console: object | None = None,
        core_name: str | None = None,
        delayable_engine: str = "default",
        parent: QtWidgets.QWidget | None = None,
        **kwargs: object,
    ) -> None:
        # Stylesheets set the theme properties one at a time, so collect them all
        # and rebuild the theme once they're done. This exists before the widget
        # does, so the property setters work whenever Qt calls them
        self._theme_values: dict[ThemeKey, ThemeValue] = {}
        self._theme_update_timer = QtCore.QTimer()
        self._theme_update_timer.setSingleShot(True)
        self._theme_update_timer.setInterval(0)

        # WorkboxMixin takes console, core_name and delayable_engine. PrEditor has
        # no type information, so mypy only sees CodeEditor's __init__
        super().__init__(  # type: ignore[call-arg]
            parent=parent,
            console=console,
            core_name=core_name,
            delayable_engine=delayable_engine,
            options=default_options(LIGHT_THEME),
            **kwargs,
        )
        self._theme_update_timer.setParent(self)
        self._theme_update_timer.timeout.connect(self.rebuild_theme)

        self._encoding: str | None = None
        self.__set_console__(console)
        install_default_behaviors(self)

        self._window_stylesheet = "Bright"
        window = self.window()
        if hasattr(window, "styleSheetChanged"):
            window.styleSheetChanged.connect(self.update_color_scheme)
        if hasattr(window, "_stylesheet"):
            self.update_color_scheme(window._stylesheet)

    def update_color_scheme(self, stylesheet: str) -> None:
        if stylesheet == self._window_stylesheet:
            return
        self._window_stylesheet = stylesheet
        self._theme_update_timer.start()

    def _base_theme(self) -> Theme:
        """Pick the built-in theme that stylesheet properties are layered on top of"""
        bg = self._theme_values.get(("gui", "bg"))
        if isinstance(bg, QtGui.QColor) and bg.isValid():
            return DARK_THEME if bg.lightness() < 128 else LIGHT_THEME
        if str(self._window_stylesheet).lower() == "dark":
            return DARK_THEME
        return LIGHT_THEME

    def build_theme(self) -> tuple[GuiColors, SyntaxSpecs]:
        """Build the gui colors and syntax specs from the built-in theme and any
        theme properties set by the stylesheet

        Returns:
            colors: The gui color dictionary
            syntax: The syntax spec dictionary
        """
        col, syn = read_theme(self._base_theme())

        syn_colors: SyntaxSpecs = {}
        styles: dict[str, set[str]] = {}
        for (section, key), value in self._theme_values.items():
            if section == "style":
                styles[key] = set(str(value).replace(",", " ").split())
            elif not isinstance(value, QtGui.QColor) or not value.isValid():
                # The color sections only hold colors, and invalid means unset
                continue
            elif section == "gui":
                col[key] = _color_to_hex(value)
            else:
                syn_colors[key] = {"color": _color_to_hex(value)}

        syn = overlay_syntax(syn, syn_colors)

        # If the stylesheet defines the style lists, they take precedence
        for style, names in styles.items():
            lookup = {n: True for n in names}
            for name, spec in syn.items():
                matched = resolve_capture(name, lookup) is not None
                if style == "italic":
                    spec["italic"] = matched
                else:
                    spec["bold"] = matched

        return col, syn

    def rebuild_theme(self) -> None:
        col, syn = self.build_theme()
        # This only redraws the editor if the theme changed
        self.options.update({"syntax": syn, "colors": col})

        # Make sure that preditor doesn't override the colors with its stylesheet
        bg, fg, sel = (
            _color_to_css(gui_color(col, name)) for name in ("bg", "fg", "selection")
        )
        ss = (
            f"QWidget {{background-color: {bg};}}\n"
            f"QPlainTextEdit {{color: {fg}; selection-background-color: {sel};}}"
        )
        # Setting the stylesheet re-polishes the widget, which re-applies the
        # theme properties. Avoid doing that unless something actually changed
        if self.styleSheet() != ss:
            self.setStyleSheet(ss)

    def setText(self, text: str) -> None:
        """Replace the text. WorkboxMixin calls the QTextEdit method name"""
        self.setPlainText(text)

    def __num_lines__(self) -> int:
        return self.document().blockCount()

    def __auto_complete_enabled__(self) -> bool:
        return self.get_behavior(TabCompletion) is not None

    def __set_auto_complete_enabled__(self, state: bool) -> None:
        if state == self.__auto_complete_enabled__():
            return
        if state:
            install_tab_completion(self)
        else:
            self.remove_behavior(TabCompletion)

    def __clear__(self) -> None:
        self.clear()
        self.__set_last_saved_text__(self.__text__())

    def __populate_edit_menu__(self, menu: QtWidgets.QMenu) -> None:
        """Fill PrEditor's Workbox menu, which it clears before every time it's shown

        The menu isn't opened at a point in the text, so the actions that work
        on a place in the document use the text cursor
        """
        self.populate_edit_menu(menu)

    def __copy_indents_as_spaces__(self) -> bool:
        """Whether copying code converts its leading tabs to spaces"""
        return self.options["copy_indents_as_spaces"]

    def __set_copy_indents_as_spaces__(self, state: bool) -> None:
        self.options["copy_indents_as_spaces"] = state

    def __cursor_position__(self) -> tuple[int, int]:
        """Returns the line and index of the cursor."""
        cursor = self.textCursor()
        sc = QtGui.QTextCursor(self.document())
        sc.setPosition(cursor.selectionStart())
        return sc.blockNumber(), sc.positionInBlock()

    def _clamped_block(self, line: int) -> QtGui.QTextBlock:
        """Get the block of a 0-based line, clamped to the document's lines"""
        doc = self.document()
        return doc.findBlockByNumber(max(0, min(line, doc.blockCount() - 1)))

    def __set_cursor_position__(self, line: int, index: int) -> None:
        """Put a single cursor at an index into a 0-based line

        The line is clamped to the document, and the index to the line
        """
        self.cursors.clear_secondary()
        block = self._clamped_block(line)
        cursor = QtGui.QTextCursor(block)
        cursor.setPosition(block.position() + max(0, min(index, block.length() - 1)))
        self.setTextCursor(cursor)

    def __insert_text__(self, txt: str) -> None:
        self.insert_text(txt)

    def __remove_selected_text__(self) -> None:
        self.insert_text("")

    def __font__(self) -> QtGui.QFont:
        return self.options["font"]

    def __set_font__(self, font: QtGui.QFont) -> None:
        self.options["font"] = font

    def __goto_line__(self, line: int) -> None:
        """Put a single cursor at the start of a 1-based line, clamped to the document"""
        self.cursors.clear_secondary()
        self.setTextCursor(QtGui.QTextCursor(self._clamped_block(line - 1)))

    def __indentations_use_tabs__(self) -> bool:
        return self.options["indent_using_tabs"]

    def __set_indentations_use_tabs__(self, state: bool) -> None:
        self.options["indent_using_tabs"] = state

    def __margins_font__(self) -> QtGui.QFont:
        """The gutters use the editor font"""
        return self.options.get("font", self.font())

    def __set_margins_font__(self, font: QtGui.QFont) -> None:
        """The gutters use the editor font, so there is no separate margin font"""

    def __tab_width__(self) -> int:
        return self.options["space_indent_width"]

    def __set_tab_width__(self, width: int) -> None:
        self.options["space_indent_width"] = width

    def __text__(self) -> str:
        return self.toPlainText()

    def __selected_text__(
        self, start_of_line: bool = False, selectText: bool = False
    ) -> tuple[str, int]:
        """The selected text, or the cursor's line if nothing is selected

        Args:
            start_of_line: Extend the selection back to the start of its first line
            selectText: Select the cursor's line, when nothing is selected

        Returns:
            The text, and the line it starts on
        """
        cursor = self.textCursor()

        # The line the selection starts on, counting wrapped and folded lines as one
        line = self.document().findBlock(cursor.selectionStart()).blockNumber()

        if cursor.selection().isEmpty():
            text = cursor.block().text()

            if selectText:
                cursor.select(QtGui.QTextCursor.SelectionType.LineUnderCursor)
                self.setTextCursor(cursor)

            return text, line

        if start_of_line:
            sc = QtGui.QTextCursor(self.document())
            sc.setPosition(cursor.selectionStart())
            sc.movePosition(MO.StartOfLine, MM.MoveAnchor)
            sc.setPosition(cursor.selectionEnd(), MM.KeepAnchor)

            return sc.selection().toPlainText(), line

        return cursor.selection().toPlainText(), line

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        # PrEditor's own shortcuts come before the editor's keys
        if not self.process_shortcut(event):
            super().keyPressEvent(event)

    def _set_theme_value(self, theme_key: ThemeKey, value: ThemeValue) -> None:
        if self._theme_values.get(theme_key) == value:
            return
        self._theme_values[theme_key] = value
        self._theme_update_timer.start()

    # fmt: off
    # GUI colors, named after GUI_COLOR_DEFAULTS and DERIVED_GUI_COLORS in
    # gui_colors.py
    guiBg                  = _theme_property("gui", "bg")
    guiBgDim               = _theme_property("gui", "bg_dim")
    guiFg                  = _theme_property("gui", "fg")
    guiFgDim               = _theme_property("gui", "fg_dim")
    guiGutter              = _theme_property("gui", "gutter")
    guiGutterFg            = _theme_property("gui", "gutter_fg")
    guiHlDim               = _theme_property("gui", "hl_dim")
    guiMatchHl             = _theme_property("gui", "match_hl")
    guiMenu                = _theme_property("gui", "menu")
    guiOutsideBg           = _theme_property("gui", "outside_bg")
    guiPairHl              = _theme_property("gui", "pair_hl")
    guiPrimaryCursor       = _theme_property("gui", "primary_cursor")
    guiSecondaryCursor     = _theme_property("gui", "secondary_cursor")
    guiSelection           = _theme_property("gui", "selection")
    guiSecondarySelection  = _theme_property("gui", "secondary_selection")

    # Syntax colors named after the treesitter captures. Unset captures fall back to
    # their parent group, so hlKeywordReturn falls back to hlKeyword
    hlAttribute            = _theme_property("syntax", "attribute")
    hlAttributeBuiltin     = _theme_property("syntax", "attribute.builtin")
    hlBoolean              = _theme_property("syntax", "boolean")
    hlCharacterSpecial     = _theme_property("syntax", "character.special")
    hlComment              = _theme_property("syntax", "comment")
    hlConstant             = _theme_property("syntax", "constant")
    hlConstantBuiltin      = _theme_property("syntax", "constant.builtin")
    hlConstructor          = _theme_property("syntax", "constructor")
    hlFunction             = _theme_property("syntax", "function")
    hlFunctionBuiltin      = _theme_property("syntax", "function.builtin")
    hlFunctionCall         = _theme_property("syntax", "function.call")
    hlFunctionMacro        = _theme_property("syntax", "function.macro")
    hlFunctionMethod       = _theme_property("syntax", "function.method")
    hlFunctionMethodCall   = _theme_property("syntax", "function.method.call")
    hlKeyword              = _theme_property("syntax", "keyword")
    hlKeywordConditional   = _theme_property("syntax", "keyword.conditional")
    hlKeywordCoroutine     = _theme_property("syntax", "keyword.coroutine")
    hlKeywordDirective     = _theme_property("syntax", "keyword.directive")
    hlKeywordException     = _theme_property("syntax", "keyword.exception")
    hlKeywordFunction      = _theme_property("syntax", "keyword.function")
    hlKeywordImport        = _theme_property("syntax", "keyword.import")
    hlKeywordOperator      = _theme_property("syntax", "keyword.operator")
    hlKeywordRepeat        = _theme_property("syntax", "keyword.repeat")
    hlKeywordReturn        = _theme_property("syntax", "keyword.return")
    hlKeywordType          = _theme_property("syntax", "keyword.type")
    hlModule               = _theme_property("syntax", "module")
    hlModuleBuiltin        = _theme_property("syntax", "module.builtin")
    hlNone                 = _theme_property("syntax", "none")
    hlNumber               = _theme_property("syntax", "number")
    hlNumberFloat          = _theme_property("syntax", "number.float")
    hlOperator             = _theme_property("syntax", "operator")
    hlPunctuation          = _theme_property("syntax", "punctuation")
    hlPunctuationBracket   = _theme_property("syntax", "punctuation.bracket")
    hlPunctuationDelimiter = _theme_property("syntax", "punctuation.delimiter")
    hlPunctuationSpecial   = _theme_property("syntax", "punctuation.special")
    hlString               = _theme_property("syntax", "string")
    hlStringDocumentation  = _theme_property("syntax", "string.documentation")
    hlStringEscape         = _theme_property("syntax", "string.escape")
    hlStringRegexp         = _theme_property("syntax", "string.regexp")
    hlType                 = _theme_property("syntax", "type")
    hlTypeBuiltin          = _theme_property("syntax", "type.builtin")
    hlTypeDefinition       = _theme_property("syntax", "type.definition")
    hlVariable             = _theme_property("syntax", "variable")
    hlVariableBuiltin      = _theme_property("syntax", "variable.builtin")
    hlVariableMember       = _theme_property("syntax", "variable.member")
    hlVariableParameter    = _theme_property("syntax", "variable.parameter")

    # Space or comma separated lists of captures to draw italic or bold.
    # Like the colors, these apply to child captures as well
    hlItalic               = _theme_property("style", "italic", "")
    hlBold                 = _theme_property("style", "bold", "")
    # fmt: on
