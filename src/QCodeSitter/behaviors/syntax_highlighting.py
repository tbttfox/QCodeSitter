from __future__ import annotations

from typing import TYPE_CHECKING

from Qt import QtGui

from ..highlighting.themes import SyntaxSpecs, resolve_capture
from ..languages import highlight_query
from ..queries import query_byte_range
from ..queries.predicates import QueryPredicates
from ..tracked_document import len16
from . import Behavior

if TYPE_CHECKING:
    from tree_sitter import Query

    from ..code_editor import CodeEditor
    from ..tracked_document import TrackedDocument
    from ..tree_manager import TreeManager


class TreeSitterHighlighter(QtGui.QSyntaxHighlighter):
    """Highlights each block with a tree-sitter query over the block's bytes

    The SyntaxHighlighting behavior only rehighlights the rows that changed
    """

    def __init__(
        self,
        document: TrackedDocument,
        tree_manager: TreeManager,
        query: Query,
        format_specs: SyntaxSpecs,
    ) -> None:
        super().__init__(document)
        self.tree_manager = tree_manager
        self._doc = document
        # Turned off while the tree doesn't match the document
        self.enabled = True
        self.query = query
        # Tree-sitter can't evaluate text predicates like #eq? and #match? on our
        # UTF-16 trees, so they are evaluated against the document text instead
        self.predicates = QueryPredicates(self._doc.node_text)
        self.formats = self._compile_formats(format_specs)

    def _compile_formats(
        self, format_specs: SyntaxSpecs
    ) -> dict[str, QtGui.QTextCharFormat]:
        """Convert the syntax specs into text formats, keyed by capture name"""
        out: dict[str, QtGui.QTextCharFormat] = {}

        for name, spec in format_specs.items():
            fmt = QtGui.QTextCharFormat()
            if "color" in spec:
                fmt.setForeground(QtGui.QColor(spec["color"]))
            if spec.get("bold"):
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            if spec.get("italic"):
                fmt.setFontItalic(True)
            out[name] = fmt

        # Captures in the query without an explicit format fall back to their
        # parent group. ie: "keyword.return" -> "keyword"
        for name in self.query_capture_names():
            if name not in out:
                fmt = resolve_capture(name, out)
                if fmt is not None:
                    out[name] = fmt

        return out

    def query_capture_names(self) -> list[str]:
        return [self.query.capture_name(i) for i in range(self.query.capture_count)]

    def _block_byte_range(
        self, block: QtGui.QTextBlock, text_len: int
    ) -> tuple[int, int]:
        """Get the UTF-16LE byte range of a block, including its newline"""
        start = self._doc.char_to_byte(block.position())
        next_block = block.next()
        if next_block.isValid():
            return start, self._doc.char_to_byte(next_block.position())
        return start, start + self._doc.char_to_byte(text_len)

    def highlightBlock(self, text: str) -> None:
        tree = self.tree_manager.tree
        block = self.currentBlock()
        if not self.enabled or tree is None or not block.isValid():
            return

        # Qt positions are UTF-16 code units, but python's len counts code points
        # so they differ when the text contains characters outside the BMP
        text_len = len16(text)
        start_byte, end_byte = self._block_byte_range(block, text_len)
        # Skip empty blocks, and blocks past the end of a tree that is out of date
        root = tree.root_node
        if start_byte >= end_byte or end_byte > root.end_byte:
            return

        captures = query_byte_range(
            self.query, root, start_byte, end_byte, self.predicates
        )
        block_start = block.position()
        for capture_name, nodes in captures.items():
            fmt = self.formats.get(capture_name)
            if fmt is None:
                continue
            for node in nodes:
                # Block-local UTF-16 positions, clamped to the block
                local_start = self._doc.byte_to_char(node.start_byte) - block_start
                local_end = self._doc.byte_to_char(node.end_byte) - block_start
                local_start, local_end = max(0, local_start), min(text_len, local_end)
                if local_end > local_start:
                    self.setFormat(local_start, local_end - local_start, fmt)


class SyntaxHighlighting(Behavior):
    """Tree-sitter syntax highlighting

    The query comes from the editor language's LanguageSpec, and the formats
    of its captures from the "syntax" option
    """

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._syntax: SyntaxSpecs = {}
        self.highlighter: TreeSitterHighlighter | None = None
        self.connect(self.editor.aboutToUndoRedo, self._on_about_to_undo_redo)
        self.connect(self.editor.undoRedoFinished, self._on_undo_redo_finished)
        self.connect(
            self.editor.tree_manager.languageChanged, self._rebuild_highlighter
        )
        self.watch_options({"syntax": self._set_syntax})

    def _on_about_to_undo_redo(self) -> None:
        # The tree is out of date until the editor reparses after the undo
        if self.highlighter:
            self.highlighter.enabled = False

    def _on_undo_redo_finished(self) -> None:
        if self.highlighter:
            self.highlighter.enabled = True
            self.highlighter.rehighlight()

    def _set_syntax(self, syntax: SyntaxSpecs) -> None:
        self._syntax = syntax
        self._rebuild_highlighter()

    def _rebuild_highlighter(self) -> None:
        """Highlight with the current language's query and the syntax formats"""
        self._detach_highlighter()
        language = self.editor.tree_manager.language
        query = highlight_query(language) if language is not None else None
        if query is None or not self._syntax:
            return
        self.highlighter = TreeSitterHighlighter(
            self.editor.document(), self.editor.tree_manager, query, self._syntax
        )
        self.editor.tree_manager.reparsed.connect(self._on_reparsed)

    def _detach_highlighter(self) -> None:
        """Stop the current highlighter from formatting the document

        The QSyntaxHighlighter is parented to the document, so dropping our
        reference isn't enough to stop it from running.
        """
        if self.highlighter is None:
            return
        self.editor.tree_manager.reparsed.disconnect(self._on_reparsed)
        self.highlighter.setDocument(None)
        self.highlighter.deleteLater()
        self.highlighter = None

    def _on_reparsed(self) -> None:
        if self.highlighter is None or not self.highlighter.enabled:
            return
        changed_rows = self.editor.tree_manager.changed_rows
        if changed_rows is None:
            self.highlighter.rehighlight()
            return

        # Only rehighlight the rows that changed instead of the whole document
        # Qt already highlighted the edited blocks with the old tree when the text
        # changed. That goes one block past the edit when text is removed, so
        # include that block too
        doc = self.editor.document()
        done: set[int] = set()
        for first, last in changed_rows:
            block = doc.findBlockByNumber(first)
            for row in range(first, last + 2):
                if not block.isValid():
                    break
                if row not in done:
                    done.add(row)
                    self.highlighter.rehighlightBlock(block)
                block = block.next()

    def remove(self) -> None:
        super().remove()
        # Detaching the highlighter from the document also clears its formats
        self._detach_highlighter()
