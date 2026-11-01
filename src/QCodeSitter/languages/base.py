from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

    from ..tracked_document import TrackedDocument
    from ..tree_manager import TreeManager


class IndentRules:
    """Syntax-aware indentation decisions for SmartIndent

    The base rules never change the indent, so the new line copies the current one.
    Rows and columns are Qt rows and UTF-16 code unit columns.
    """

    def __init__(self, tree_manager: TreeManager, document: TrackedDocument) -> None:
        self.tree_manager = tree_manager
        self.document = document

    def node_at(self, row: int, col: int) -> Node | None:
        return self.tree_manager.node_at_char(self.document.row_col_to_char(row, col))

    def should_indent_after(self, row: int, col: int) -> bool:
        """Whether a new line after this column should be indented one more level"""
        return False

    def should_dedent_after(self, row: int, col: int, line_text: str) -> bool:
        """Whether a new line after this column should be indented one less level"""
        return False


@dataclass(frozen=True)
class LanguageSpec:
    """Everything the behaviors need to know about one tree-sitter language"""

    name: str
    comment_prefix: str = "# "
    # The default highlight query for the language
    highlight_query: str = ""
    # Captures the names defined in a document, named after their kind
    identifier_query: str = ""
    # Foldable node types that end with their last line (ie: indented blocks)
    fold_hide_last_line: frozenset[str] = frozenset()
    # Foldable node types whose last line is a closing delimiter to keep showing
    fold_keep_last_line: frozenset[str] = frozenset()
    indent_rules: type[IndentRules] = IndentRules
    # Node types where typing never shows completions, like strings and comments
    no_completion_types: frozenset[str] = frozenset()
    # The string node type, and the types of its opening and closing delimiters
    string_type: str = ""
    string_delimiter_types: tuple[str, str] = ("", "")

    @property
    def foldable_types(self) -> frozenset[str]:
        return self.fold_hide_last_line | self.fold_keep_last_line
