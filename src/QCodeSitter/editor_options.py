from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypedDict, get_origin, get_type_hints

from Qt import QtCore, QtGui
from tree_sitter import Language

from .gui_colors import GuiColors
from .highlighting.themes import SyntaxSpecs

if TYPE_CHECKING:
    from collections.abc import KeysView


class OptionsDict(TypedDict, total=False):
    """Every option the editor and the built-in behaviors understand"""

    # Indentation
    space_indent_width: int
    tab_indent_width: int
    indent_using_tabs: bool
    copy_indents_as_spaces: bool
    indent_bracket_pairs: list[str]
    # Language and appearance. The highlight query comes from the language
    language: Language
    syntax: SyntaxSpecs
    colors: GuiColors
    font: QtGui.QFont
    # Tab completion
    vim_completion_keys: bool  # Ctrl+N/Ctrl+P for next/prev and Ctrl+Y to accept
    debounce_delay: int  # milliseconds
    # Brackets
    auto_bracket_pairs: str
    highlight_bracket_pairs: list[str]
    highlight_quote_pairs: str


# The value of every option that isn't given. The language and font have none
OPTION_DEFAULTS: OptionsDict = {
    "space_indent_width": 4,
    "tab_indent_width": 8,
    "indent_using_tabs": False,
    "copy_indents_as_spaces": True,
    "indent_bracket_pairs": ["()", "[]", "{}"],
    "syntax": {},
    "colors": {},
    "vim_completion_keys": True,
    "debounce_delay": 150,
    "auto_bracket_pairs": "()[]{}\"\"''``",
    "highlight_bracket_pairs": ["()", "[]", "{}"],
    "highlight_quote_pairs": "\"'`",
}

# Option key -> the runtime type its values must have
_OPTION_TYPES: dict[str, type] = {
    key: get_origin(hint) or hint for key, hint in get_type_hints(OptionsDict).items()
}
OPTION_KEYS = frozenset(_OPTION_TYPES)

# Option key -> the function that applies its value
OptionHandlers = Mapping[str, Callable[[Any], object]]


def check_option_keys(keys: Iterable[str]) -> None:
    """Raise a KeyError for any key that isn't a known option"""
    unknown = set(keys) - OPTION_KEYS
    if unknown:
        raise KeyError(f"Unknown editor options: {sorted(unknown)}")


def check_options(opts: Mapping[str, object]) -> None:
    """Raise a KeyError for unknown keys, or a TypeError for values of the wrong type"""
    check_option_keys(opts)
    for key, value in opts.items():
        expected = _OPTION_TYPES[key]
        if not isinstance(value, expected):
            raise TypeError(
                f"Editor option {key!r} must be a {expected.__name__}, "
                f"not {type(value).__name__}"
            )


class EditorOptions(QtCore.QObject):
    """The options shared by an editor and its behaviors

    Options that aren't given take their value from OPTION_DEFAULTS.
    Setting an option emits `optionsUpdated` with the keys that changed
    """

    optionsUpdated = QtCore.Signal(list)  # list of str

    def __init__(self, opts: OptionsDict | None = None) -> None:
        super().__init__()
        opts = {} if opts is None else opts
        check_options(opts)
        self._options: dict[str, Any] = {**copy.deepcopy(OPTION_DEFAULTS), **opts}

    def __getitem__(self, key: str) -> Any:
        return self._options[key]

    def __setitem__(self, key: str, value: Any) -> None:
        check_options({key: value})
        self._options[key] = value
        self.optionsUpdated.emit([key])

    def __contains__(self, key: str) -> bool:
        return key in self._options

    def update(self, opts: OptionsDict) -> None:
        check_options(opts)
        self._options.update(opts)
        self.optionsUpdated.emit(list(opts.keys()))

    def get(self, key: str, default: Any = None) -> Any:
        return self._options.get(key, default)

    def keys(self) -> KeysView[str]:
        return self._options.keys()

    def apply(self, handlers: OptionHandlers, keys: Iterable[str]) -> None:
        """Call the handler of each key that is set, with its value"""
        for key in keys:
            handler = handlers.get(key)
            if handler is not None and key in self._options:
                handler(self._options[key])
