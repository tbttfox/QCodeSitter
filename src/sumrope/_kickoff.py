import sys

path = r"C:\Users\Tyler\src\preditor_treesitter\sumrope\src"
sys.path.insert(0, path)

from sumrope.naive_document import NaiveDocument
from sumrope import SumRopeDocument

from Qt.QtWidgets import QPlainTextEdit, QDialog, QVBoxLayout, QPlainTextDocumentLayout, QApplication

app = QApplication(sys.argv)
dlg = QDialog()
lay = QVBoxLayout(dlg)
dlg.setLayout(lay)

edit = QPlainTextEdit(dlg)
mydoc = NaiveDocument(edit)
#mydoc = SumRopeDocument(edit)
doclay = QPlainTextDocumentLayout(mydoc)
mydoc.setDocumentLayout(doclay)


edit.setDocument(mydoc)
lay.addWidget(edit)
dlg.show()

app.exec_()

