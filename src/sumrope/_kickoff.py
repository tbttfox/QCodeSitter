import sys

path = r"C:\Users\Tyler\src\sumrope\src"
sys.path.insert(0, path)

from sumrope.line_editor import CodeEditor
from sumrope.behaviors.smart_indent import SmartIndent
from sumrope.behaviors.line_numbers import LineNumber
from sumrope.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from sumrope.behaviors.highlight_matching_selection import HighlightMatchingSelection
from sumrope.behaviors.syntax_highlighting import SyntaxHighlighting
from sumrope.editor_options import EditorOptions
from sumrope.hl_groups import FORMAT_SPECS
import tree_sitter_python as tspython
from tree_sitter import Language
from Qt.QtWidgets import QMainWindow, QApplication
from Qt.QtGui import QFont


app = QApplication(sys.argv)
win = QMainWindow()

options = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
        "language": Language(tspython.language()),
        "highlights": (tspython.HIGHLIGHTS_QUERY, FORMAT_SPECS),
        "font": QFont("MS Shell Dlg 2", pointSize=8),
    }
)

edit = CodeEditor(options, parent=win)

edit.replaceBehavior(SyntaxHighlighting)
edit.replaceBehavior(SmartIndent)
edit.replaceBehavior(HighlightMatchingBrackets)
edit.replaceBehavior(HighlightMatchingSelection)
edit.replaceBehavior(LineNumber)

win.setCentralWidget(edit)
win.show()

app.exec_()
