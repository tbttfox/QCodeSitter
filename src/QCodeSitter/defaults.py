"""The standard editor setup, shared by the demo, the PrEditor plugin and the tests"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tree_sitter_python as tspython
from Qt import QtGui
from tree_sitter import Language

from .behaviors.auto_bracket import AutoBracket
from .behaviors.code_folding import CodeFolding
from .behaviors.comment_toggle import CommentToggle
from .behaviors.highlight_matching_brackets import HighlightMatchingBrackets
from .behaviors.highlight_matching_selection import HighlightMatchingSelection
from .behaviors.line_numbers import LineNumber
from .behaviors.multi_cursor_paint import MultiCursorPaint
from .behaviors.overscroll import Overscroll
from .behaviors.smart_indent import SmartIndent
from .behaviors.syntax_highlighting import SyntaxHighlighting
from .behaviors.tab_completion import TabCompletion
from .behaviors.tab_completion.providers import IdentifierProvider
from .editor_options import EditorOptions
from .highlighting.themes import DARK_THEME, Theme, read_theme

if TYPE_CHECKING:
    from .behaviors import Behavior
    from .code_editor import CodeEditor

# The built-in behaviors that install_default_behaviors adds, along with
# TabCompletion, which needs its providers
DEFAULT_BEHAVIORS: tuple[type[Behavior], ...] = (
    SyntaxHighlighting,
    SmartIndent,
    HighlightMatchingBrackets,
    HighlightMatchingSelection,
    LineNumber,
    Overscroll,
    MultiCursorPaint,
    CodeFolding,
    CommentToggle,
)

# The built-in behaviors that are off by default
OPTIONAL_BEHAVIORS: tuple[type[Behavior], ...] = (AutoBracket,)


def default_options(
    theme: Theme = DARK_THEME,
    language: Language | None = None,
    font: QtGui.QFont | None = None,
) -> EditorOptions:
    """Make a new set of options for editing python, or another language

    The other options take their values from OPTION_DEFAULTS

    Args:
        theme: The color theme
        language: The tree-sitter language. Defaults to python
        font: Defaults to an 11pt system font
    """
    if language is None:
        language = Language(tspython.language())
    if font is None:
        font = QtGui.QFont("MS Shell Dlg 2", pointSize=11)
    colors, syntax = read_theme(theme)
    return EditorOptions(
        {"language": language, "syntax": syntax, "colors": colors, "font": font}
    )


def install_tab_completion(editor: CodeEditor) -> TabCompletion:
    """Add tab completion, completing the names defined in the document"""
    completion = editor.add_behavior(TabCompletion)
    completion.add_provider(IdentifierProvider)
    return completion


def install_default_behaviors(editor: CodeEditor, optional: bool = False) -> None:
    """Add tab completion and DEFAULT_BEHAVIORS to an editor

    Args:
        editor: The editor to add the behaviors to
        optional: Also add the OPTIONAL_BEHAVIORS
    """
    install_tab_completion(editor)
    for behavior_cls in DEFAULT_BEHAVIORS + (OPTIONAL_BEHAVIORS if optional else ()):
        editor.add_behavior(behavior_cls)
