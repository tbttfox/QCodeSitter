import logging

import tree_sitter_python as tspython
from tree_sitter import Language
from Qt import QtWidgets, QtGui

from ..code_editor import CodeEditor
from ..behaviors.smart_indent import SmartIndent
from ..behaviors.line_numbers import LineNumber
from ..behaviors.overscroll import Overscroll
from ..behaviors.highlight_matching_selection import HighlightMatchingSelection
from ..behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from ..behaviors.syntax_highlighting import SyntaxHighlighting
from ..behaviors.auto_bracket import AutoBracket
from ..behaviors.tab_completion import TabCompletion
from ..behaviors.providers.identifiers import IdentifierProvider
from ..behaviors.code_folding import CodeFolding
from ..behaviors.multi_cursor_paint import MultiCursorPaint
from ..editor_options import EditorOptions
from ..hl_groups import FORMAT_SPECS, COLORS
from ..highlight_query import HIGHLIGHT_QUERY


from preditor.workbox_mixin import WorkboxMixin


logger = logging.getLogger(__name__)


class WorkboxTextEdit(WorkboxMixin, CodeEditor):
    """A very simple multi-line text editor without any bells and whistles.

    It's better than nothing, but not by much.
    """

    _warning_text = (
        "This is a bare bones workbox, if you have another option, it's probably"
        "a better option."
    )

    def __init__(
        self,
        console=None,
        core_name=None,
        delayable_engine="default",
        parent=None,
        options=None,
    ):
        if options is None:
            options = EditorOptions()

        WorkboxMixin.__init__(self, parent=parent, core_name=core_name)
        CodeEditor.__init__(self, options, parent=parent)

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
        self.addBehavior(AutoBracket)
        self.addBehavior(CodeFolding)

    def __auto_complete_enabled__(self):
        for bh in enumerate(self._behaviors):
            if type(bh) is TabCompletion:
                return True
        return False

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

    def __comment_toggle__(self):
        pass
        # self.comment_toggle()

    def keyPressEvent(self, event):
        if self.process_shortcut(event):
            return
        else:
            super(WorkboxTextEdit, self).keyPressEvent(event)
