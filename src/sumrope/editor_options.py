from Qt.QtCore import QObject, Signal
from typing import Optional, Any


class EditorOptions(QObject):
    optionsUpdated = Signal(list)  # list of str

    def __init__(self, opts: Optional[dict[str, Any]] = None):
        super().__init__()
        if opts is None:
            opts = {}
        self._options: dict[str, Any] = opts

    def __getitem__(self, key: str):
        return self._options[key]

    def __setitem__(self, key: str, value):
        self._options[key] = value
        self.optionsUpdated.emit([key])

    def __contains__(self, key: str) -> bool:
        return key in self._options

    def update(self, opts: dict[str, Any]):
        self._options.update(opts)
        self.optionsUpdated.emit(list(opts.keys()))

    def get(self, key, default=None) -> Any:
        return self._options.get(key, default)

    def keys(self):
        return self._options.keys()
