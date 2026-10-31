from __future__ import annotations

from typing import TYPE_CHECKING, Any

from Qt import QtGui
from tree_sitter import Query

from ..hl_groups import resolve_capture
from ..query_predicates import QueryPredicates, document_node_text, prepare_query_source
from ..ts_version_fix import query_byte_range
from ..utils import len16
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor
    from ..line_tracker import TrackedDocument
    from ..tree_manager import TreeManager


class TreeSitterHighlighter(QtGui.QSyntaxHighlighter):
    """
    Tree-sitter based syntax highlighter using incremental rehighlighting
    restricted to changed byte ranges.
    """

    def __init__(
        self,
        document: TrackedDocument,
        tree_manager: TreeManager,
        highlights_query_source: str,
        format_specs: dict[str, dict[str, Any]],
    ):
        super().__init__(document)
        self.tree_manager = tree_manager
        self._doc: TrackedDocument = document
        self._enabled = True  # Flag to temporarily disable highlighting

        parser = self.tree_manager.parser
        if parser is None:
            raise RuntimeError("The tree parser must be properly set")
        lang = parser.language
        if lang is None:
            raise RuntimeError("The tree language must be properly set")

        # The tree is parsed from a callback, so tree-sitter can't read the node text
        # for predicates like #eq? and #match?. We evaluate those ourselves
        self.query = Query(lang, prepare_query_source(highlights_query_source))
        self.predicates = QueryPredicates(
            lambda node: document_node_text(self._doc, node)
        )
        self.formats = self._compile_formats(format_specs)

    def setDocument(self, doc: TrackedDocument):
        self._doc = doc
        super().setDocument(doc)

    # ------------------------------------------------------------------
    # Text formats
    # ------------------------------------------------------------------

    def _compile_formats(
        self, format_specs: dict[str, dict[str, Any]]
    ) -> dict[str, QtGui.QTextCharFormat]:
        """Convert user style specs -> QtGui.QTextCharFormat instances."""
        out = {}

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

    # ------------------------------------------------------------------
    # QtGui.QSyntaxHighlighter entry point
    # ------------------------------------------------------------------
    def highlightBlock(self, text: str):
        # Quick exit if highlighting is disabled
        if not self._enabled:
            return

        if self.tree_manager.tree is None:
            return

        block = self.currentBlock()
        if not block.isValid():
            return

        # Qt positions are UTF-16 code units, but python's len counts code points
        # so they differ when the text contains characters outside the BMP
        text_len = len16(text)

        # Each UTF-16 code unit is 2 bytes. The end includes the newline if there is one
        block_start_char = block.position()
        block_start_byte = block_start_char * 2
        next_block = block.next()
        if next_block.isValid():
            block_end_byte = next_block.position() * 2
        else:
            block_end_byte = block_start_byte + text_len * 2

        # Skip highlighting for empty blocks (can happen during undo to empty document)
        if block_start_byte >= block_end_byte:
            return

        # Validate that tree is still valid for this document state
        # If the tree's byte range doesn't cover our block, skip highlighting
        root = self.tree_manager.tree.root_node
        if root is None or block_end_byte > root.end_byte:
            # Tree is stale, skip highlighting until tree updates
            return

        captures = query_byte_range(
            self.query, root, block_start_byte, block_end_byte, self.predicates
        )
        if captures is None:
            return

        for capture_name, nodes in captures.items():
            fmt = self.formats.get(capture_name)
            if fmt is None:
                continue
            for node in nodes:
                # Skip nodes that are beyond the current document
                # (can happen during undo when tree has stale nodes)
                if node.start_byte > block_end_byte:
                    continue

                # Convert to block-local UTF-16 positions, clamped to [0, text_len]
                local_start = max(0, node.start_byte // 2 - block_start_char)
                local_end = min(text_len, node.end_byte // 2 - block_start_char)
                if local_end > local_start:
                    self.setFormat(local_start, local_end - local_start, fmt)


class SyntaxHighlighting(Behavior):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"highlights"})
        self._highlights = None
        self.highlighter: TreeSitterHighlighter | None = None
        self.editor.behaviorPrepareUndo.connect(self.prepareUndoRedo)
        self.editor.behaviorPrepareRedo.connect(self.prepareUndoRedo)
        self.editor.behaviorAfterUndoRedo.connect(self.afterUndoRedo)
        self.updateAll()

    def prepareUndoRedo(self):
        """Disable highlighting before undo/redo to prevent stale tree issues"""
        if self.highlighter:
            self.highlighter._enabled = False

    def afterUndoRedo(self):
        """Update tree and rehighlight after undo/redo completes"""
        if self.highlighter:
            # Update the tree first
            self.editor.tree_manager.fullUpdate()
            # Re-enable highlighting and rehighlight
            self.highlighter._enabled = True
            self.highlighter.rehighlight()

    @property
    def highlights(self):
        return self._highlights

    @highlights.setter
    def highlights(self, value):
        self._highlights = value
        self._detachHighlighter()
        if not value:
            return

        if self.editor.tree_manager.parser is None:
            return

        if self.editor.tree_manager.parser.language is None:
            return

        hlquery, fmts = value
        self.highlighter = TreeSitterHighlighter(
            self.editor._doc, self.editor.tree_manager, hlquery, fmts
        )
        self.editor.tree_manager.reparsed.connect(self._on_reparsed)

    def _detachHighlighter(self):
        """Stop the current highlighter from formatting the document

        The QSyntaxHighlighter is parented to the document, so dropping our
        reference isn't enough to stop it from running.
        """
        if self.highlighter is None:
            return
        try:
            self.editor.tree_manager.reparsed.disconnect(self._on_reparsed)
        except (RuntimeError, TypeError):
            pass
        self.highlighter.setDocument(None)
        self.highlighter.deleteLater()
        self.highlighter = None

    def _on_reparsed(self):
        if self.highlighter is None:
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

    def remove(self):
        super().remove()
        self.editor.behaviorPrepareUndo.disconnect(self.prepareUndoRedo)
        self.editor.behaviorPrepareRedo.disconnect(self.prepareUndoRedo)
        self.editor.behaviorAfterUndoRedo.disconnect(self.afterUndoRedo)
        # Detaching the highlighter from the document also clears its formats
        self._detachHighlighter()
