import sys

path = r"C:\Users\Tyler\src\preditor_treesitter\sumrope\src"
sys.path.insert(0, path)

from sumrope.naive_document import NaiveDocument
from sumrope.line_editor import CodeEditor
from sumrope import SumRopeDocument

from Qt.QtWidgets import QPlainTextEdit, QDialog, QMainWindow, QVBoxLayout, QPlainTextDocumentLayout, QApplication

app = QApplication(sys.argv)
win = QMainWindow()

#edit = QPlainTextEdit(parent=win)
edit = CodeEditor(parent=win)
print(edit)

win.setCentralWidget(edit)

#mydoc = NaiveDocument(edit)
mydoc = SumRopeDocument(edit)
doclay = QPlainTextDocumentLayout(mydoc)
mydoc.setDocumentLayout(doclay)


edit.setDocument(mydoc)
win.show()

app.exec_()

