"""The built-in completion providers"""

from __future__ import annotations

import inspect
import sys

from ...languages import identifier_query
from ...tree_manager import query_byte_range
from .types import Completion, Provider


class IdentifierProvider(Provider):
    """Completes the names defined in the document

    The names come from the identifier query of the editor language's LanguageSpec
    """

    PRIORITY = 3

    def provide(self) -> set[Completion]:
        tree = self.editor.tree_manager.tree
        if tree is None:
            return set()
        query = identifier_query(tree.language)
        if query is None:
            return set()

        captures = query_byte_range(query, tree.root_node, 0, tree.root_node.end_byte)
        doc = self.editor.document()
        identifiers = set()
        for capture_name, nodes in captures.items():
            for node in nodes:
                name = doc.node_text(node)
                if name.isidentifier():
                    identifiers.add(Completion(name, capture_name, self.PRIORITY))
        return identifiers


def _kind_of(value: object) -> str:
    if inspect.ismodule(value):
        return "module"
    if isinstance(value, type):
        return "class"
    if callable(value):
        return "function"
    return "variable"


class MainPythonProvider(Provider):
    """Completes the names in the running python's __main__ namespace

    Useful when the editor is a console for the python process it runs in
    """

    PRIORITY = 3

    def provide(self) -> set[Completion]:
        namespace = vars(sys.modules["__main__"])
        return {
            Completion(name, _kind_of(value), self.PRIORITY)
            for name, value in namespace.items()
        }
