from __future__ import annotations

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Any

from ..editor_options import check_option_keys

if TYPE_CHECKING:
    from Qt import QtGui, QtWidgets

    from ..code_editor import CodeEditor
    from ..editor_options import EditorOptions, OptionHandlers


class Behavior:
    """A feature that plugs into a CodeEditor

    Subclasses usually call `watch_options` and then `apply_all_options` in
    their __init__, and undo everything they connected in `remove`.
    """

    def __init__(self, editor: CodeEditor) -> None:
        self.editor: CodeEditor = editor
        self.options: EditorOptions = editor.options
        self._option_handlers: dict[str, Callable[[Any], object]] = {}
        self.options.optionsUpdated.connect(self._on_options_updated)
        self.shortcut_actions: list[QtWidgets.QAction] = []

    def watch_options(self, handlers: OptionHandlers) -> None:
        """Call these handlers with the new value whenever their option changes

        Keep a default for each option, because handlers are only called for
        options that are set. Raises a KeyError for unknown option keys
        """
        check_option_keys(handlers)
        self._option_handlers.update(handlers)

    def apply_all_options(self) -> None:
        """Call every option handler, once the editor has applied its own options"""
        if self.editor.is_loaded:
            self.options.apply(self._option_handlers, list(self._option_handlers))

    def _on_options_updated(self, keys: Collection[str]) -> None:
        self.options.apply(self._option_handlers, keys)

    def remove(self) -> None:
        """Disconnect from the editor. Subclasses should call this too"""
        self.options.optionsUpdated.disconnect(self._on_options_updated)

    def get_hotkeys(self) -> list[QtWidgets.QAction]:
        """The shortcut actions to add to the editor"""
        return []

    def has_key_press(self) -> bool:
        """Whether the editor should pass key presses to `handle_key_press`"""
        return False

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """Handle a key press, before the editor's own key handling

        This runs inside an edit session. A behavior can handle the key for
        some cursors and not others: calling `editor.citer.cursor_completed()`
        for a cursor stops the handlers after this one from editing it.

        Returns:
            True to consume the key, so the handlers after this one never see it
        """
        raise NotImplementedError("Behaviors with has_key_press must implement this")
