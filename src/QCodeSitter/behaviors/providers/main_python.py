from __future__ import annotations
import inspect
from . import Provider
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..tab_completion import Completion


class MainPythonProvider(Provider):
    def provide(self) -> set[Completion]:
        """Extract identifiers from the document's tree"""
        import __main__

        identifiers: set[Completion] = set()
        for name, val in __main__.__dict__.items():
            kind = "variable"
            if callable(val):
                kind = "function"
            elif inspect.ismodule(val):
                kind = "module"
            elif isinstance(val, type):
                kind = "class"

            identifiers.add(
                Completion(
                    text=name,
                    kind=kind,
                    priority=3,
                )
            )
        return identifiers
