from tree_sitter import Language, Parser, Tree, Point
from typing import Callable, Optional


class TreeManager:
    """Manages the tree-sitter parse tree with incremental updates

    This class owns the parse tree and provides a shared resource for both
    syntax highlighting and syntax analysis. It supports incremental updates
    to efficiently re-parse only the changed portions of the document.
    """

    def __init__(
        self, language: Language, source_callback: Callable[[int, Point], bytes]
    ):
        """Initialize the tree manager

        Args:
            language: The tree-sitter Language to use for parsing
            source_callback: Callback function to provide source bytes to the parser.
                           Signature: (byte_offset: int, point: Point) -> bytes
        """
        self.parser = Parser(language)
        self.tree: Optional[Tree] = None
        self._source_callback = source_callback

    def update(
        self,
        start_byte: int,
        old_end_byte: int,
        new_end_byte: int,
        start_point: Point,
        old_end_point: Point,
        new_end_point: Point,
    ) -> Optional[Tree]:
        """Incrementally update the parse tree after document changes

        Args:
            start_byte: Byte offset where the change started
            old_end_byte: Byte offset where the change ended (before change)
            new_end_byte: Byte offset where the change ends (after change)
            start_point: (row, column) where the change started
            old_end_point: (row, column) where the change ended (before change)
            new_end_point: (row, column) where the change ends (after change)
        """
        old_tree = self.tree
        if self.tree is not None:
            self.tree.edit(
                start_byte=start_byte,
                old_end_byte=old_end_byte,
                new_end_byte=new_end_byte,
                start_point=start_point,
                old_end_point=old_end_point,
                new_end_point=new_end_point,
            )
            self.tree = self.parser.parse(self._source_callback, self.tree)
        else:
            # First parse - no old tree to pass
            self.tree = self.parser.parse(self._source_callback)
        return old_tree

    def get_node_at_point(self, byte_offset: int):
        """Get the AST node at a specific byte offset

        Args:
            byte_offset: The byte offset in the document

        Returns:
            The tree-sitter Node at the given offset, or None if no tree exists
        """
        if self.tree is None:
            return None
        return self.tree.root_node.descendant_for_byte_range(byte_offset, byte_offset)

    @property
    def root_node(self):
        """Get the root node of the parse tree

        Returns:
            The root Node of the tree, or None if no tree exists
        """
        return self.tree.root_node if self.tree else None
