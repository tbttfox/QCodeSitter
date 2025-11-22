import sys

path = r'D:\temp\preditor_treesitter\sumrope\src'
if path not in sys.path:
    sys.path.insert(0, path)

todel = [m for m in sys.modules if 'sumrope' in m]
for d in todel:
    del sys.modules[d]





run_workbox('sumrope/reload')
import preditor

from sumrope import (
    ChunkedLineTracker,
    SingleLineHighlighter,
    PythonSyntaxHighlighter,
    SumRopeDocument,
    FORMAT_SPECS,
)

from Qt.QtWidgets import QPlainTextEdit, QDialog, QVBoxLayout, QPlainTextDocumentLayout

inst = preditor.instance()

dlg = QDialog(inst)
lay = QVBoxLayout(dlg)
dlg.setLayout(lay)

edit = QPlainTextEdit(dlg)
mydoc = SumRopeDocument(edit)
doclay = QPlainTextDocumentLayout(mydoc)
mydoc.setDocumentLayout(doclay)


edit.setDocument(mydoc)
lay.addWidget(edit)
dlg.show()
