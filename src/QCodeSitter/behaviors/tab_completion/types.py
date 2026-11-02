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
    """Where the cursor is, and what it is completing

    The columns are str indexes into `line`, not Qt positions
    """

    line_num: int  # 0-indexed line number
    index: int  # The cursor's column
    prefix: str  # The identifier being completed, before the cursor
    start: int  # The column the prefix starts at
    line: str  # The text of the cursor's line
    node: Node | None  # Tree-sitter node at the cursor


class Provider:
    """A source of completions for TabCompletion"""

    def __init__(self, editor: CodeEditor) -> None:
        self.editor = editor

    def provide(self, context: CompletionContext) -> set[Completion]:
        """The completions for the identifier at the cursor

        The popup only shows the ones that start with `context.prefix`, so
        returning more is fine
        """
        raise NotImplementedError("A Provider must override the .provide() method")
