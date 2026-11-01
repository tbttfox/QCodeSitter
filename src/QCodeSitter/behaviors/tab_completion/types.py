from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

    from ...code_editor import CodeEditor


@dataclass(frozen=True)
class Completion:
    """A single completion result

    Equal names of the same kind are one completion, whatever their priority
    """

    text: str  # Completion text (e.g., "path")
    kind: str  # "function", "class", "variable", "module", etc.
    # For sorting (higher = more important)
    priority: int = field(compare=False)

    def display(self) -> str:
        return f"{self.text} ({self.kind})"


@dataclass
class CompletionContext:
    """Where the cursor is, and what it is completing"""

    line_num: int  # 0-indexed line number
    char_col: int  # str index of the cursor in the line
    prefix: str  # The identifier being completed, before the cursor
    start: int  # str index of the start of the prefix
    full_line: str
    node: Node | None  # Tree-sitter node at the cursor


class Provider:
    """A source of completions for TabCompletion"""

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor

    def provide(self) -> set[Completion]:
        raise NotImplementedError("A Provider must override the .provide() method")
