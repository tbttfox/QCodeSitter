"""A tree-sitter powered code editor widget for Qt

`default_options` and `install_default_behaviors` come from the defaults module,
which is only imported when one of them is used, because it loads every
built-in behavior and the python grammar
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .code_editor import CodeEditor
from .editor_options import EditorOptions
from .tracked_document import TrackedDocument
from .tree_manager import TreeManager

if TYPE_CHECKING:
    from .defaults import default_options, install_default_behaviors

_FROM_DEFAULTS = ("default_options", "install_default_behaviors")


def __getattr__(name: str) -> Any:
    if name in _FROM_DEFAULTS:
        from . import defaults

        return getattr(defaults, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CodeEditor",
    "EditorOptions",
    "TrackedDocument",
    "TreeManager",
    "default_options",
    "install_default_behaviors",
]
