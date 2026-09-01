import logging

from functools import partial
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt import QtGui, QtCore

from ..code_editor import CodeEditor
from ..behaviors.smart_indent import SmartIndent
from ..behaviors.line_numbers import LineNumber
from ..behaviors.overscroll import Overscroll
from ..behaviors.highlight_matching_selection import HighlightMatchingSelection
from ..behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from ..behaviors.comment_toggle import CommentToggle
from ..behaviors.syntax_highlighting import SyntaxHighlighting
from ..behaviors.auto_bracket import AutoBracket
from ..behaviors.tab_completion import TabCompletion
from ..behaviors.providers.identifiers import IdentifierProvider
from ..behaviors.code_folding import CodeFolding
from ..behaviors.multi_cursor_paint import MultiCursorPaint
from ..editor_options import EditorOptions
from ..hl_groups import DARK_THEME, LIGHT_THEME, read_theme
from ..highlight_query import HIGHLIGHT_QUERY


from preditor.gui.workbox_mixin import WorkboxMixin


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
        return self._color_properties(attrName, default)

    def _setattr(attrName, self, value):
        return self._set_color_properties(attrName, value)

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
        self._color_properties = {}
        self._color_tracker = set()

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
        theme = LIGHT_THEME
        if self._windowStyleSheet.lower() == "dark":
            theme = DARK_THEME
        col, syn = read_theme(theme)
        self.options["highlights"] = (HIGHLIGHT_QUERY, syn)
        self.options["colors"] = col

        # Make sure that preditor doesn't override the bg color
        # with its stylesheet...
        # Maybe I can move to stylesheets in the future???
        bgcolor = QtGui.QColor(col["bg"])
        bgc = (bgcolor.red(), bgcolor.green(), bgcolor.blue())
        ss = f"QWidget {{background-color: rgb{bgc}}}"
        self.setStyleSheet(ss)

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
            super(CodeSitterTextEdit, self).keyPressEvent(event)

    def _color_properties(self, attrName, default):
        return self._color_properties.get(attrName, default)

    def _set_color_properties(self, attrName, value):
        self._color_properties[attrName] = value
        self._color_upate_timer.start()
        self._color_tracker.add(attrName)

    def _color_properties_updated(self):
        ud = {k: self._color_properties[k] for k in self._color_tracker}
        print(ud)
        self._color_tracker = set()

    # fmt: off
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
    # fmt: on
