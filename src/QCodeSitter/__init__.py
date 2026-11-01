"""A tree-sitter powered code editor widget for Qt"""

from .code_editor import CodeEditor
from .defaults import default_options, install_default_behaviors
from .editor_options import EditorOptions
from .tracked_document import TrackedDocument
from .tree_manager import TreeManager

__all__ = [
    "CodeEditor",
    "EditorOptions",
    "TrackedDocument",
    "TreeManager",
    "default_options",
    "install_default_behaviors",
]
