from __future__ import annotations

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Any

from ..editor_options import check_option_keys

if TYPE_CHECKING:
    from Qt import QtCore, QtGui, QtWidgets

    from ..code_editor import CodeEditor
    from ..editor_options import EditorOptions, OptionHandlers


class Behavior:
    """A feature that plugs into a CodeEditor

    Subclasses get their options with `watch_options`, and connect to the
    editor's signals with `connect` so that `remove` disconnects them, and undo
    anything else they did to the editor in `on_remove`.
    Behaviors that handle keys override `handle_key_press`.
    """

    # The editor passes key presses to the behaviors with the highest priority first.
    # Behaviors of the same priority get them in the order they were added
    KEY_PRIORITY = 0

    def __init__(self, editor: CodeEditor) -> None:
        self.editor: CodeEditor = editor
        self.options: EditorOptions = editor.options
        self._option_handlers: dict[str, Callable[[Any], object]] = {}
        self._connections: list[tuple[QtCore.SignalInstance, Callable[..., Any]]] = []
        self.shortcut_actions: list[QtWidgets.QAction] = []
        self.connect(self.options.optionsUpdated, self._on_options_updated)

    @classmethod
    def handles_key_presses(cls) -> bool:
        """Whether the editor should pass key presses to `handle_key_press`"""
        return cls.handle_key_press is not Behavior.handle_key_press

    def connect(
        self,
        signal: QtCore.SignalInstance,
        slot: Callable[..., Any],
        conn_type: QtCore.Qt.ConnectionType | None = None,
    ) -> None:
        """Connect a signal to a slot until the behavior is removed"""
        if conn_type is None:
            signal.connect(slot)
        else:
            signal.connect(slot, conn_type)
        self._connections.append((signal, slot))

    def watch_options(self, handlers: OptionHandlers) -> None:
        """Call these handlers with their option's value now, and whenever it changes

        Every option has a value except the language and font, whose handlers
        wait until they are set. Raises a KeyError for unknown option keys
        """
        check_option_keys(handlers)
        self._option_handlers.update(handlers)
        self.options.apply(handlers, handlers)

    def _on_options_updated(self, keys: Collection[str]) -> None:
        self.options.apply(self._option_handlers, keys)

    def remove(self) -> None:
        """Disconnect from the editor, then call `on_remove`

        Subclasses override `on_remove` instead of this
        """
        for signal, slot in reversed(self._connections):
            signal.disconnect(slot)
        self._connections.clear()
        self.on_remove()

    def on_remove(self) -> None:
        """Undo what the behavior did to the editor, besides connecting signals

        This runs after the signals connected with `connect` are
        disconnected, so the cleanup can't trigger the behavior's own handlers
        """

    def get_hotkeys(self) -> list[QtWidgets.QAction]:
        """The shortcut actions to add to the editor"""
        return []

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """Handle a key press, before the editor's own key handling

        This runs inside an edit session. A behavior can handle the key for
        some cursors and not others: calling `editor.citer.mark_cursor_completed()`
        for a cursor stops the handlers after this one from editing it.

        Returns:
            True to consume the key, so the handlers after this one never see it
        """
        return False
