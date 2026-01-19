# fmt: off
import sys
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt import QtWidgets, QtGui

from QCodeSitter.code_editor import CodeEditor
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.overscroll import Overscroll
from QCodeSitter.behaviors.highlight_matching_selection import HighlightMatchingSelection
from QCodeSitter.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.auto_bracket import AutoBracket
# from QCodeSitter.behaviors.tab_completion import TabCompletion
# from QCodeSitter.behaviors.providers.identifiers import IdentifierProvider
from QCodeSitter.behaviors.code_folding import CodeFolding
from QCodeSitter.behaviors.multi_cursor_paint import MultiCursorPaint
from QCodeSitter.editor_options import EditorOptions
from QCodeSitter.hl_groups import FORMAT_SPECS, COLORS
from QCodeSitter.highlight_query import HIGHLIGHT_QUERY
# fmt: on


app = QtWidgets.QApplication(sys.argv)
win = QtWidgets.QMainWindow()

options = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
        "language": Language(tspython.language()),
        "highlights": (HIGHLIGHT_QUERY, FORMAT_SPECS),
        "colors": COLORS,
        "font": QtGui.QFont("MS Shell Dlg 2", pointSize=11),
        "vim_completion_keys": True,  # c-n c-p for next/prev  c-y for accept
        "debounce_delay": 150,  # in milliseconds
        "auto_bracket_enabled": True,
        "auto_bracket_pairs": "()[]{}\"\"''``",
        "indent_bracket_pairs": ["()", "[]", "{}"],
    }
)

edit = CodeEditor(options, parent=win)

"""
_old, cmp_bh = edit.addBehavior(TabCompletion)
cmp_bh.addProvider(IdentifierProvider)
"""

# TODO: There's an error when undoing multiple multi-edit inputs with syntax highlighting turned on
# I'm guessing it has to do with the undo_requested syntax re-highlighting
# TODO: Fix Bug in delete_word_backward when the cursor is at the end of the document
# TODO: Group normal text editing into undo groups by word

edit.addBehavior(SyntaxHighlighting)
edit.addBehavior(SmartIndent)
edit.addBehavior(HighlightMatchingBrackets)
edit.addBehavior(HighlightMatchingSelection)
edit.addBehavior(LineNumber)
edit.addBehavior(Overscroll)
edit.addBehavior(MultiCursorPaint)
edit.addBehavior(AutoBracket)
edit.addBehavior(CodeFolding)

win.setCentralWidget(edit)
win.show()

app.exec_()
