import sys

path = r"C:\Users\Tyler\src\preditor_treesitter\sumrope\src"
sys.path.insert(0, path)

from sumrope.line_editor import CodeEditor
from sumrope.behaviors.smart_indent import SmartIndent
from sumrope.behaviors.line_numbers import LineNumber
from sumrope.behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from sumrope.behaviors.highlight_matching_selection import HighlightMatchingSelection
from sumrope.editor_options import EditorOptions

from Qt.QtWidgets import QMainWindow, QApplication

app = QApplication(sys.argv)
win = QMainWindow()

options = EditorOptions(
    {
        "space_indent_width": 4,
        "tab_indent_width": 8,
        "indent_using_tabs": False,
    }
)

edit = CodeEditor(options, parent=win)

edit.addBehavior(SmartIndent(edit))
edit.addBehavior(HighlightMatchingBrackets(edit))
edit.addBehavior(HighlightMatchingSelection(edit))
edit.addBehavior(LineNumber(edit))


win.setCentralWidget(edit)
win.show()

app.exec_()
