from __future__ import annotations
from ..tab_completion import Completion, TabCompletion


class Provider:
    def __init__(self, tabcomplete: TabCompletion):
        self.tabcomplete = tabcomplete

    def provide(self) -> set[Completion]:
        raise NotImplementedError("A Provider must override the .provide() method")
