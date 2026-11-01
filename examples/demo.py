"""Open a window with a fully featured editor. Run with `python examples/demo.py`"""

import sys

from Qt import QtWidgets

from QCodeSitter import CodeEditor, default_options, install_default_behaviors


def build_window() -> QtWidgets.QMainWindow:
    win = QtWidgets.QMainWindow()
    editor = CodeEditor(default_options(), parent=win)
    install_default_behaviors(editor, optional=True)
    win.setCentralWidget(editor)
    return win


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    win = build_window()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
