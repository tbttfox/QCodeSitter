from __future__ import annotations
from . import Behavior
from typing import TYPE_CHECKING, Optional
from Qt import QtGui, QtWidgets
from tree_sitter import Point

if TYPE_CHECKING:
    from ..line_editor import CodeEditor

from ..line_highlighter import TreeSitterHighlighter


class SyntaxHighlighting(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"highlights"})
        self._highlights = None
        self.highlighter: Optional[TreeSitterHighlighter] = None
        self.updateAll()

    @property
    def highlights(self):
        return self._highlights

    @highlights.setter
    def highlights(self, value):
        if not value:
            self.highlighter = None
            return
        hlquery, fmts = value
        self.highlighter = TreeSitterHighlighter(
            self.editor._doc, self.editor.tree_manager, hlquery, fmts
        )
