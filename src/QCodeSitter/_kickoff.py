import sys

path = r"C:\blur\dev\GitHub\QCodeSitter\src"
sys.path.insert(0, path)

# fmt: off
from QCodeSitter.line_editor import CodeEditor
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from QCodeSitter.behaviors.highlight_matching_selection import HighlightMatchingSelection
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.auto_bracket import AutoBracket
from QCodeSitter.behaviors.tab_completion import TabCompletion
from QCodeSitter.behaviors.providers.identifiers import IdentifierProvider
from QCodeSitter.behaviors.code_folding import CodeFolding
from QCodeSitter.editor_options import EditorOptions
from QCodeSitter.hl_groups import FORMAT_SPECS, COLORS
from QCodeSitter.highlight_query import HIGHLIGHT_QUERY
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt.QtWidgets import QMainWindow, QApplication
from Qt.QtGui import QFont
# fmt: on


app = QApplication(sys.argv)
win = QMainWindow()

options = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
        "language": Language(tspython.language()),
        # "highlights": (tspython.HIGHLIGHTS_QUERY, FORMAT_SPECS),
        "highlights": (HIGHLIGHT_QUERY, FORMAT_SPECS),
        "colors": COLORS,
        "font": QFont("MS Shell Dlg 2", pointSize=11),
        "vim_completion_keys": True,  # c-n c-p for next/prev  c-y for accept
        "debounce_delay": 150,  # in milliseconds
    }
)

edit = CodeEditor(options, parent=win)

_old, cmp_bh = edit.addBehavior(TabCompletion)
cmp_bh.addProvider(IdentifierProvider)

edit.addBehavior(SyntaxHighlighting)
edit.addBehavior(SmartIndent)
edit.addBehavior(HighlightMatchingBrackets)
edit.addBehavior(HighlightMatchingSelection)
edit.addBehavior(LineNumber)
edit.addBehavior(AutoBracket)
edit.addBehavior(CodeFolding)


win.setCentralWidget(edit)
win.show()

app.exec_()
