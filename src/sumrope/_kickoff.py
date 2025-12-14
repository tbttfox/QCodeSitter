import os
import sys

path = r"C:\Users\Tyler\src\sumrope\src"
sys.path.insert(0, path)

from sumrope.line_editor import CodeEditor
from sumrope.behaviors.smart_indent import SmartIndent
from sumrope.behaviors.line_numbers import LineNumber
from sumrope.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from sumrope.behaviors.highlight_matching_selection import HighlightMatchingSelection
from sumrope.behaviors.syntax_highlighting import SyntaxHighlighting
from sumrope.behaviors.tab_completion import TabCompletion
from sumrope.behaviors.providers.identifiers import IdentifierProvider
from sumrope.editor_options import EditorOptions
from sumrope.hl_groups import FORMAT_SPECS, COLORS
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt.QtWidgets import QMainWindow, QApplication
from Qt.QtGui import QFont


app = QApplication(sys.argv)
win = QMainWindow()

HL_QUERY = open(os.path.join(path, "sumrope","highlights.scm"), 'r').read()


options = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
        "language": Language(tspython.language()),
        #"highlights": (tspython.HIGHLIGHTS_QUERY, FORMAT_SPECS),
        "highlights": (HL_QUERY, FORMAT_SPECS),

        "colors": COLORS,
        "font": QFont("MS Shell Dlg 2", pointSize=8),
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


win.setCentralWidget(edit)
win.show()

app.exec_()
