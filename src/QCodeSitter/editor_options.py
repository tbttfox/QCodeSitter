from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypedDict,
    get_origin,
    get_type_hints,
    overload,
)

from Qt import QtCore, QtGui
from tree_sitter import Language

from .gui_colors import GuiColors
from .highlighting.themes import SyntaxSpecs

if TYPE_CHECKING:
    from collections.abc import KeysView


class OptionsDict(TypedDict, total=False):
    """Every option the editor and the built-in behaviors understand

    Behaviors from outside the package add their options with `register_option`
    """

    # Indentation
    space_indent_width: int
    tab_indent_width: int
    indent_using_tabs: bool
    copy_indents_as_spaces: bool
    # Opening and closing characters, like ["()", "[]"]
    indent_bracket_pairs: list[str]
    # Language and appearance. The highlight query comes from the language
    language: Language
    syntax: SyntaxSpecs
    colors: GuiColors
    font: QtGui.QFont
    # Tab completion
    vim_completion_keys: bool  # Ctrl+N/Ctrl+P for next/prev and Ctrl+Y to accept
    debounce_delay: int  # milliseconds
    # Brackets, as pairs of opening and closing characters
    auto_bracket_pairs: list[str]
    highlight_bracket_pairs: list[str]
    # The characters that open and close strings, like "'\""
    highlight_quote_chars: str


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
    "auto_bracket_pairs": ["()", "[]", "{}", '""', "''", "``"],
    "highlight_bracket_pairs": ["()", "[]", "{}"],
    "highlight_quote_chars": "\"'`",
}

# The keys of the built-in options
OPTION_KEYS = frozenset(get_type_hints(OptionsDict))

# Option key -> the function that applies its value
OptionHandlers = Mapping[str, Callable[[Any], object]]


class OptionSchema:
    """The type every option's values must have, and the registered options' defaults

    The built-in options come from OptionsDict, and behaviors from outside the
    package add theirs with `register`
    """

    def __init__(self) -> None:
        self._types: dict[str, type] = {
            key: get_origin(hint) or hint
            for key, hint in get_type_hints(OptionsDict).items()
        }
        self._defaults: dict[str, Any] = {}

    def register(self, key: str, value_type: type, default: object = None) -> None:
        """Add an option, for a behavior from outside the package

        Args:
            key: The option's name, which mustn't be a built-in option
            value_type: The type its values must have
            default: Its value when it isn't set. None means it has no default,
                and handlers for it wait until it is set
        """
        if key in OPTION_KEYS:
            raise ValueError(f"{key!r} is a built-in editor option")
        self._types[key] = value_type
        self._defaults.pop(key, None)
        if default is not None:
            self.check({key: default})
            self._defaults[key] = default

    def unregister(self, key: str) -> None:
        """Remove an option added with `register`"""
        if key in OPTION_KEYS:
            raise ValueError(f"{key!r} is a built-in editor option")
        self._types.pop(key, None)
        self._defaults.pop(key, None)

    def registered_default(self, key: str) -> Any:
        """A copy of a registered option's default. Raises a KeyError if it has none"""
        return copy.deepcopy(self._defaults[key])

    def check_keys(self, keys: Iterable[str]) -> None:
        """Raise a KeyError for any key that isn't a known option"""
        unknown = set(keys) - set(self._types)
        if unknown:
            raise KeyError(f"Unknown editor options: {sorted(unknown)}")

    def check(self, opts: Mapping[str, object]) -> None:
        """Raise a KeyError for unknown keys, or a TypeError for wrong value types"""
        self.check_keys(opts)
        for key, value in opts.items():
            expected = self._types[key]
            if not isinstance(value, expected):
                raise TypeError(
                    f"Editor option {key!r} must be a {expected.__name__}, "
                    f"not {type(value).__name__}"
                )


# There is one schema for the process, so a registered option works in every editor
OPTION_SCHEMA = OptionSchema()
register_option = OPTION_SCHEMA.register
unregister_option = OPTION_SCHEMA.unregister
check_option_keys = OPTION_SCHEMA.check_keys
check_options = OPTION_SCHEMA.check


class EditorOptions(QtCore.QObject):
    """The options shared by an editor and its behaviors

    Options that aren't given take their value from OPTION_DEFAULTS, or from
    the default they were registered with. Setting options emits
    `optionsUpdated` with the keys whose value changed
    """

    optionsUpdated = QtCore.Signal(list)  # list of str

    def __init__(self, opts: OptionsDict | None = None) -> None:
        super().__init__()
        opts = {} if opts is None else opts
        check_options(opts)
        self._options: dict[str, Any] = {**copy.deepcopy(OPTION_DEFAULTS), **opts}

    def _has(self, key: str) -> bool:
        """Whether the option has a value, taking a registered default if needed"""
        if key not in self._options:
            try:
                self._options[key] = OPTION_SCHEMA.registered_default(key)
            except KeyError:
                return False
        return True

    if TYPE_CHECKING:
        # Reading a built-in option gives the type OptionsDict declares for it
        # fmt: off
        @overload
        def __getitem__(self, key: Literal["space_indent_width", "tab_indent_width", "debounce_delay"]) -> int: ...
        @overload
        def __getitem__(self, key: Literal["indent_using_tabs", "copy_indents_as_spaces", "vim_completion_keys"]) -> bool: ...
        @overload
        def __getitem__(self, key: Literal["indent_bracket_pairs", "auto_bracket_pairs", "highlight_bracket_pairs"]) -> list[str]: ...
        @overload
        def __getitem__(self, key: Literal["highlight_quote_chars"]) -> str: ...
        @overload
        def __getitem__(self, key: Literal["language"]) -> Language: ...
        @overload
        def __getitem__(self, key: Literal["syntax"]) -> SyntaxSpecs: ...
        @overload
        def __getitem__(self, key: Literal["colors"]) -> GuiColors: ...
        @overload
        def __getitem__(self, key: Literal["font"]) -> QtGui.QFont: ...
        @overload
        def __getitem__(self, key: str) -> Any: ...
        # fmt: on

    def __getitem__(self, key: str) -> Any:
        if not self._has(key):
            raise KeyError(key)
        return self._options[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.update({key: value})

    def __contains__(self, key: str) -> bool:
        return self._has(key)

    def update(self, opts: Mapping[str, Any]) -> None:
        """Set several options, emitting `optionsUpdated` once for the changed ones"""
        check_options(opts)
        changed = [
            key
            for key, value in opts.items()
            if key not in self._options or self._options[key] != value
        ]
        self._options.update(opts)
        if changed:
            self.optionsUpdated.emit(changed)

    def get(self, key: str, default: Any = None) -> Any:
        return self._options[key] if self._has(key) else default

    def keys(self) -> KeysView[str]:
        return self._options.keys()

    def apply(self, handlers: OptionHandlers, keys: Iterable[str]) -> None:
        """Call the handler of each key that is set, with its value"""
        for key in keys:
            handler = handlers.get(key)
            if handler is not None and self._has(key):
                handler(self._options[key])
