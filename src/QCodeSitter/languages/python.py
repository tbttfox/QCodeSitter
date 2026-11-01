from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ..utils import leading_whitespace
from .base import IndentRules, LanguageSpec
from .python_highlights import HIGHLIGHT_QUERY

if TYPE_CHECKING:
    from tree_sitter import Node

# Statements whose body starts after a colon
_BLOCK_TYPES = frozenset(
    {
        "if_statement",
        "for_statement",
        "while_statement",
        "function_definition",
        "class_definition",
        "with_statement",
        "try_statement",
        "except_clause",
        "finally_clause",
        "elif_clause",
        "else_clause",
        "match_statement",
        "case_clause",
    }
)
_COLLECTION_TYPES = frozenset(
    {"list", "dictionary", "set", "tuple", "argument_list", "parameters"}
)
# Statements that end their block, so the next line dedents
_TERMINAL_TYPES = frozenset(
    {
        "return_statement",
        "break_statement",
        "continue_statement",
        "pass_statement",
        "raise_statement",
    }
)
_OPEN_BRACKETS = frozenset("([{")
_CLOSE_BRACKETS = frozenset(")]}")


def _child_of_type(node: Node, types: Collection[str]) -> Node | None:
    for child in node.children:
        if child.type in types:
            return child
    return None


def _opens_block(node: Node, row: int) -> bool:
    """Whether this node starts an indented block or open bracket on the row"""
    if node.type in _BLOCK_TYPES:
        # The colon can be followed by a comment, like "def foo():  # comment"
        colon = _child_of_type(node, (":",))
        return colon is not None and colon.start_point.row == row
    if node.type in _OPEN_BRACKETS:
        # Incomplete code can leave a bare bracket in an ERROR node
        return node.start_point.row == row
    if node.type in _COLLECTION_TYPES:
        opening = _child_of_type(node, _OPEN_BRACKETS)
        closing = _child_of_type(node, _CLOSE_BRACKETS)
        if opening is None or opening.start_point.row != row:
            return False
        return closing is None or closing.start_point.row != row
    return False


class PythonIndentRules(IndentRules):
    def should_indent_after(self, row: int, col: int) -> bool:
        node = self.node_at(row, col)
        while node is not None:
            if _opens_block(node, row):
                return True
            node = node.parent
        return False

    def should_dedent_after(self, row: int, col: int, line_text: str) -> bool:
        node = self.node_at(row, col)
        if node is None:
            return False
        if self._closes_earlier_bracket(row, col, line_text):
            return True
        while node is not None:
            if node.type in _TERMINAL_TYPES:
                return True
            node = node.parent
        return False

    def _closes_earlier_bracket(self, row: int, col: int, line_text: str) -> bool:
        """Whether the line starts with a bracket, after the column, that closes
        a bracket opened on an earlier line
        """
        # The indent is all whitespace, so its length is also its UTF-16 length
        bracket_col = len(leading_whitespace(line_text))
        if line_text[bracket_col : bracket_col + 1] not in _CLOSE_BRACKETS:
            return False
        # Enter after the bracket keeps the indent of the closing line
        if col >= bracket_col:
            return False
        bracket = self.node_at(row, bracket_col)
        if bracket is None or bracket.parent is None:
            return False
        opening = _child_of_type(bracket.parent, _OPEN_BRACKETS)
        return opening is not None and opening.start_point.row < row


IDENTIFIER_QUERY = """
(function_definition name: (identifier) @function)
(class_definition name: (identifier) @class)
(assignment left: (identifier) @variable)
(parameters (identifier) @parameter)
(import_statement name: (dotted_name (identifier) @import))
(import_from_statement name: (dotted_name (identifier) @import))
(aliased_import name: (dotted_name (identifier) @import))
(aliased_import alias: (identifier) @import)
"""

PYTHON = LanguageSpec(
    name="python",
    comment_prefix="# ",
    highlight_query=HIGHLIGHT_QUERY,
    identifier_query=IDENTIFIER_QUERY,
    fold_hide_last_line=frozenset(
        {
            "class_definition",
            "for_statement",
            "function_definition",
            "if_statement",
            "match_statement",
            "try_statement",
            "while_statement",
            "with_statement",
        }
    ),
    fold_keep_last_line=frozenset({"argument_list", "dictionary", "list", "tuple"}),
    indent_rules=PythonIndentRules,
    no_completion_types=frozenset({"string", "comment", "string_start", "string_end"}),
    string_type="string",
    string_delimiter_types=("string_start", "string_end"),
)
