from __future__ import annotations

from typing import TYPE_CHECKING

from ..cursors.line_edits import replace_lines_at_cursors
from ..languages import language_spec
from ..utils import leading_whitespace, make_shortcut_action
from . import Behavior

if TYPE_CHECKING:
    from Qt import QtWidgets


class CommentToggle(Behavior):
    """Toggle line comments for the current line or selection (Ctrl+/)

    The comment prefix comes from the editor language's LanguageSpec
    """

    @property
    def comment_prefix(self) -> str:
        return language_spec(self.editor.tree_manager.language).comment_prefix

    def get_hotkeys(self) -> list[QtWidgets.QAction]:
        return [
            make_shortcut_action(
                self.editor, "Ctrl+/", self.toggle_comment, "Toggle Comment"
            )
        ]

    def toggle_comment(self) -> None:
        prefix = self.comment_prefix
        with self.editor.edit_session():
            replace_lines_at_cursors(
                self.editor.citer, lambda lines: self.toggle_lines(lines, prefix)
            )

    @classmethod
    def toggle_lines(cls, lines: list[str], prefix: str) -> list[str]:
        """Uncomment the lines if every non-blank one is commented, otherwise comment them"""
        filled = [line for line in lines if line.strip()]
        if all(cls._line_is_commented(line, prefix) for line in filled):
            return [cls._uncomment_line(line, prefix) for line in lines]
        # Line the comments up at the smallest indent
        min_indent = min((len(leading_whitespace(line)) for line in filled), default=0)
        return [cls._comment_line(line, prefix, min_indent) for line in lines]

    @staticmethod
    def _line_is_commented(line: str, prefix: str) -> bool:
        # Without its trailing space, so "#foo" counts as commented too
        return line.lstrip().startswith(prefix.rstrip())

    @staticmethod
    def _comment_line(line: str, prefix: str, min_indent: int) -> str:
        if not line.strip():
            return line
        return line[:min_indent] + prefix + line[min_indent:]

    @staticmethod
    def _uncomment_line(line: str, prefix: str) -> str:
        indent = len(leading_whitespace(line))
        rest = line[indent:]
        # Also handle the prefix without its trailing space, like "#foo"
        for p in (prefix, prefix.rstrip()):
            if rest.startswith(p):
                return line[:indent] + rest[len(p) :]
        return line
