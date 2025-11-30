import sys

path = r"C:\Users\Tyler\src\preditor_treesitter\sumrope\src"
sys.path.insert(0, path)

from sumrope.line_editor import CodeEditor

from Qt.QtWidgets import QMainWindow, QApplication

app = QApplication(sys.argv)
win = QMainWindow()

#edit = QPlainTextEdit(parent=win)
edit = CodeEditor(parent=win)
print(edit)

win.setCentralWidget(edit)
win.show()

app.exec_()

