from __future__ import annotations
from tree_sitter import Query
from typing import Optional
from ..tab_completion import Completion, TabCompletion
from ...constants import ENC
from . import Provider
from ..ts_version_fix import query_byte_range


class IdentifierProvider(Provider):
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
    # TODO: Get id queries for non-python languages from the editorOptions
    # Also, pull Providers out into their own files

    def __init__(self, tabcomplete: TabCompletion):
        super().__init__(tabcomplete)
        self.query: Optional[Query] = None

        tree = self.tabcomplete.last_tree
        if tree is None:
            return

        self.query = Query(tree.language, self.IDENTIFIER_QUERY)

    def provide(self) -> set[Completion]:
        """Extract identifiers from the document's tree"""
        tree = self.tabcomplete.last_tree
        if tree is None:
            return set()

        if self.query is None:
            self.query = Query(tree.language, self.IDENTIFIER_QUERY)

        # Set the byte range for the query cursor
        captures = query_byte_range(
            self.query,
            tree.root_node,
            0,
            tree.root_node.end_byte,
        )

        identifiers = set()
        if captures is None:
            return identifiers

        for capture_name, nodes in captures.items():
            for node in nodes:
                if node.text is None:
                    continue

                name = node.text.decode(ENC)
                # Skip empty or invalid identifiers
                if name and name.isidentifier():
                    identifiers.add(
                        Completion(
                            text=name,
                            kind=capture_name,
                            priority=3,
                        )
                    )
        return identifiers
