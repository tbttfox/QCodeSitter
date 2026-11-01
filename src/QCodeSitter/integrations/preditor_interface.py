from __future__ import annotations

from typing import Literal

from preditor.gui.workbox_mixin import WorkboxMixin
from Qt import QtCore, QtGui

from .. import CodeEditor, default_options, install_default_behaviors
from ..behaviors.tab_completion import TabCompletion
from ..defaults import install_tab_completion
from ..gui_colors import GuiColors, gui_color
from ..highlighting.themes import (
    DARK_THEME,
    LIGHT_THEME,
    SyntaxSpecs,
    Theme,
    overlay_syntax,
    read_theme,
    resolve_capture,
)
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
        console=None,
        core_name=None,
        delayable_engine="default",
        parent=None,
        **kwargs,
    ) -> None:
        self.options = default_options(LIGHT_THEME)
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
        self._theme_update_timer.timeout.connect(self.rebuild_theme)
        self._theme_values: dict[ThemeKey, ThemeValue] = {}

        self._encoding = None
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
        bg: QtGui.QColor = self.guiBg
        if bg.isValid():
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
            if isinstance(value, str):
                # Only the "style" section holds capture name lists
                styles[key] = set(value.replace(",", " ").split())
            elif not value.isValid():
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

        # Only update the options if they changed, because that redraws the editor
        if self.options["syntax"] != syn:
            self.options["syntax"] = syn
        if self.options["colors"] != col:
            self.options["colors"] = col

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
        """The WorkboxMixin assumes a QTextEdit, not a QPlainTextEdit
        So I have to reroute setText to setPlainText"""
        self.setPlainText(text)

    def __num_lines__(self) -> int:
        return self.document().blockCount()

    def __text_part__(self, lineNum=None, start=None, end=None) -> str:
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

    def __copy_indents_as_spaces__(self) -> bool:
        """When copying code, should it convert leading tabs to spaces?"""
        return self.options["copy_indents_as_spaces"]

    def __set_copy_indents_as_spaces__(self, state: bool) -> None:
        self.options["copy_indents_as_spaces"] = state

    def __cursor_position__(self) -> tuple[int, int]:
        """Returns the line and index of the cursor."""
        cursor = self.textCursor()
        sc = QtGui.QTextCursor(self.document())
        sc.setPosition(cursor.selectionStart())
        return sc.blockNumber(), sc.positionInBlock()

    def __font__(self) -> QtGui.QFont:
        return self.options["font"]

    def __set_font__(self, font: QtGui.QFont) -> None:
        self.options["font"] = font

    def __goto_line__(self, line) -> None:
        self.cursors.clear_secondary()
        cursor = QtGui.QTextCursor(self.document().findBlockByNumber(line - 1))
        self.setTextCursor(cursor)

    def __indentations_use_tabs__(self) -> bool:
        return self.options["indent_using_tabs"]

    def __set_indentations_use_tabs__(self, state: bool) -> None:
        self.options["indent_using_tabs"] = state

    def __margins_font__(self) -> QtGui.QFont:
        return QtGui.QFont()

    def __set_margins_font__(self, font: QtGui.QFont) -> None:
        """The gutters use the editor font, so there is no separate margin font"""

    def __tab_width__(self) -> int:
        return self.options["space_indent_width"]

    def __text__(self) -> str:
        return self.toPlainText()

    def __selected_text__(
        self, start_of_line=False, selectText=False
    ) -> tuple[str, int]:
        cursor = self.textCursor()

        # The line the selection starts on, counting wrapped and folded lines as one
        line = self.document().findBlock(cursor.selectionStart()).blockNumber()

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
            sc.movePosition(MO.StartOfLine, MM.MoveAnchor)
            sc.setPosition(cursor.selectionEnd(), MM.KeepAnchor)

            return sc.selection().toPlainText(), line

        return self.textCursor().selection().toPlainText(), line

    def keyPressEvent(self, event) -> None:
        if self.process_shortcut(event):
            return
        else:
            super().keyPressEvent(event)

    def _set_theme_value(self, theme_key: ThemeKey, value: ThemeValue) -> None:
        if self._theme_values.get(theme_key) == value:
            return
        self._theme_values[theme_key] = value
        self._theme_update_timer.start()

    # fmt: off
    # GUI colors. See highlighting/themes.py for how these are used
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
    guiVisual              = _theme_property("gui", "visual")

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
