from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypeVar

from Qt import QtCore, QtGui

from ...languages import language_spec
from ...tracked_document import utf16_to_index
from ...utils import KEY, MOD
from .. import Behavior
from .popup import CompletionPopup
from .types import Completion, CompletionContext, Provider

if TYPE_CHECKING:
    from ...code_editor import CodeEditor

T_Provider = TypeVar("T_Provider", bound=Provider)

MIN_PREFIX_LENGTH = 2


def is_identifier_char(char: str) -> bool:
    """Whether a character can be part of an identifier, like a letter or digit"""
    return char.isalnum() or char == "_"


def identifier_before(line: str, index: int) -> tuple[int, str]:
    """Get the identifier that ends at a str index in the line

    Returns:
        The str index where the identifier starts
        The identifier, like "jo" in "os.path.jo|"
    """
    start = index
    while start > 0 and is_identifier_char(line[start - 1]):
        start -= 1
    return start, line[start:index]


def context_at_cursor(editor: CodeEditor) -> CompletionContext:
    """Get the completion context at the editor's primary cursor"""
    cursor = editor.textCursor()
    block = cursor.block()
    line = block.text()
    index = utf16_to_index(line, cursor.positionInBlock())
    start, prefix = identifier_before(line, index)
    return CompletionContext(
        line_num=block.blockNumber(),
        index=index,
        prefix=prefix,
        start=start,
        line=line,
        node=editor.tree_manager.node_at_char(cursor.position()),
    )


def merge_completions(completions: Iterable[Completion]) -> set[Completion]:
    """Merge the completions of the same name and kind, keeping the highest priority"""
    best: dict[Completion, Completion] = {}
    for comp in completions:
        current = best.get(comp)
        if current is None or comp.priority > current.priority:
            best[comp] = comp
    return set(best.values())


class TabCompletion(Behavior):
    """Shows a completion popup while typing an identifier

    Completions come from the providers added with `add_provider`. Tab or
    Enter accepts the selected completion, and Up/Down change it.
    """

    # Tab and Enter accept a completion before SmartIndent can indent with them
    KEY_PRIORITY = 10

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._providers: list[Provider] = []
        # Where the shown completions were asked for, or None before the first time
        self._last_context: CompletionContext | None = None
        # Whether the text changed since the cursor last moved, so moving
        # the cursor around without typing doesn't open the popup
        self._typing_mode = False

        self.connect(self.editor.cursorPositionChanged, self.on_cursor_changed)
        self.connect(self.editor.textChanged, self.on_text_changed)

        # Wait for a pause in typing before asking the providers
        self.debounce_timer = QtCore.QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.refresh_completions)

        self.completion_popup = CompletionPopup(self.editor)
        self.watch_options({"colors": self.completion_popup.set_colors})

    def add_provider(self, provider_cls: type[T_Provider]) -> T_Provider:
        provider = provider_cls(self.editor)
        self._providers.append(provider)
        return provider

    def remove(self) -> None:
        super().remove()
        self.debounce_timer.stop()
        self.completion_popup.hide()
        self.completion_popup.deleteLater()

    def on_text_changed(self) -> None:
        self._typing_mode = True

    def _showing_completions_for(self, context: CompletionContext) -> bool:
        """Whether the popup is showing the completions for the identifier at context

        Once the popup hides, the next identifier asks the providers again
        """
        return (
            self.completion_popup.isVisible()
            and self._last_context is not None
            and context.line_num == self._last_context.line_num
            and context.start == self._last_context.start
        )

    def on_cursor_changed(self) -> None:
        context = context_at_cursor(self.editor)
        if not self._should_trigger(context):
            self.completion_popup.hide()
        elif self._showing_completions_for(context):
            # Still completing the same word, so just filter what's showing
            self.completion_popup.update_filter(context.prefix)
            self._last_context = context
        elif self._typing_mode:
            self.debounce_timer.start(self.options["debounce_delay"])
        self._typing_mode = False

    def _should_trigger(self, context: CompletionContext) -> bool:
        """Whether the cursor is at the end of a long enough identifier, in code"""
        spec = language_spec(self.editor.tree_manager.language)
        if context.node is not None and context.node.type in spec.no_completion_types:
            return False
        if is_identifier_char(context.line[context.index : context.index + 1]):
            # In the middle of an identifier
            return False
        prefix = context.prefix
        return len(prefix) >= MIN_PREFIX_LENGTH and (
            prefix[0].isalpha() or prefix[0] == "_"
        )

    def refresh_completions(self) -> None:
        """Show the completions for the identifier at the cursor

        This asks the providers for the completions of a new identifier, and
        only filters the shown ones while still typing the same identifier.
        It runs once typing pauses for the "debounce_delay" option
        """
        # The context might have changed while waiting
        context = context_at_cursor(self.editor)
        if not self._should_trigger(context):
            self.completion_popup.hide()
            return

        if self._showing_completions_for(context):
            self.completion_popup.update_filter(context.prefix)
        else:
            completions = merge_completions(
                comp
                for provider in self._providers
                for comp in provider.provide(context)
            )
            self.completion_popup.show_completions(completions, context.prefix)
        self._last_context = context

    # ------------------------------------------------------------------
    # Keys. Each returns whether to consume the key
    # ------------------------------------------------------------------

    def accept_item(self) -> bool:
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.accept_completion()
        return True

    def select_previous(self) -> bool:
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.offset_current(-1)
        return True

    def select_next(self) -> bool:
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.offset_current(1)
        return True

    def dismiss(self) -> bool:
        """Hide the popup, consuming the key if it was showing"""
        if not self.completion_popup.isVisible():
            return False
        self.completion_popup.hide()
        return True

    def dismiss_and_pass_key(self) -> bool:
        """Hide the popup, and let the key through"""
        self.completion_popup.hide()
        return False

    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        actions = {
            KEY.Key_Return: self.accept_item,
            KEY.Key_Enter: self.accept_item,
            KEY.Key_Tab: self.accept_item,
            KEY.Key_Up: self.select_previous,
            KEY.Key_Down: self.select_next,
            KEY.Key_Escape: self.dismiss,
            KEY.Key_Backspace: self.dismiss_and_pass_key,
        }
        vim_keys = self.options["vim_completion_keys"]
        if vim_keys and event.modifiers() & MOD.ControlModifier:
            actions.update(
                {
                    KEY.Key_Y: self.accept_item,
                    KEY.Key_P: self.select_previous,
                    KEY.Key_N: self.select_next,
                }
            )
        action = actions.get(event.key())
        return action() if action is not None else False


__all__ = [
    "Completion",
    "CompletionContext",
    "CompletionPopup",
    "Provider",
    "TabCompletion",
    "context_at_cursor",
    "identifier_before",
]
