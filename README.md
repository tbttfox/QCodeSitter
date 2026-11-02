# QCodeSitter

A reusable, tree-sitter-powered code editor widget for Qt applications. QCodeSitter provides a `QPlainTextEdit` subclass with syntax highlighting, multi-cursor editing, smart indentation, code folding, and more -- all driven by a modular plugin system that makes it easy to add, remove, or customize features.

This is not an IDE. It's a drop-in editor widget you can embed in your own Qt application.

## Quick Start

The quickest way to a full editor is the default setup:

```python
from Qt import QtWidgets

from QCodeSitter import CodeEditor, default_options, install_default_behaviors

app = QtWidgets.QApplication([])
editor = CodeEditor(default_options())
install_default_behaviors(editor)
editor.show()
app.exec()
```

`install_default_behaviors(editor, optional=True)` also adds the behaviors that are off by
default, like `AutoBracket`.

Or pick the options and behaviors yourself:

```python
from tree_sitter import Language
import tree_sitter_python as tspython
from Qt import QtGui

from QCodeSitter import CodeEditor, EditorOptions
from QCodeSitter.highlighting.themes import DARK_THEME, read_theme
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumbers
from QCodeSitter.behaviors.auto_bracket import AutoBracket

language = Language(tspython.language())
colors, syntax = read_theme(DARK_THEME)
options = EditorOptions({
    "space_indent_width": 4,
    "indent_using_tabs": False,
    "language": language,
    "syntax": syntax,
    "colors": colors,
    "font": QtGui.QFont("Consolas", pointSize=11),
})

editor = CodeEditor(options)
editor.add_behavior(SyntaxHighlighting)
editor.add_behavior(SmartIndent)
editor.add_behavior(LineNumbers)
editor.add_behavior(AutoBracket)
```

You only pay for what you use. If you don't need code folding, don't add it. If you want custom behavior, write your own.

Every option is listed in `OptionsDict` in `editor_options.py`, and the options you don't
give take their value from `OPTION_DEFAULTS`. Setting an option that isn't listed raises a
`KeyError`, and a value of the wrong type raises a `TypeError`, so mistakes don't silently
do nothing. The highlight query comes from the language, so changing `"language"` is all it
takes to highlight another language. `"syntax"` only holds the format of each capture.

The `"colors"` option holds the gui colors, listed with their defaults in `gui_colors.py`.

Setting an option to the value it already has does nothing, so change a list option by
setting a new list rather than editing it in place. A behavior from outside the package
adds its own options with `register_option("my_option", int, default=3)`.

## The Behavior System

Every editor feature beyond basic text editing is implemented as a **Behavior**. Behaviors are essentially just plugins. They are modular, self-contained classes that plug into the editor through a well-defined interface.

### Base Class

All behaviors inherit from `Behavior`:

```python
from QCodeSitter.behaviors import Behavior

class MyBehavior(Behavior):
    def __init__(self, editor):
        super().__init__(editor)
        # self.editor  - the CodeEditor instance
        # self.options  - the EditorOptions dict-like object
        # Signals connected with self.connect are disconnected when it's removed
        self.connect(editor.textChanged, self.on_text_changed)

    def on_text_changed(self):
        ...

    def remove(self):
        # Undo anything else done in __init__
        super().remove()
```

Behaviors are added and removed at runtime:

```python
behavior = editor.add_behavior(MyBehavior)  # Replaces any existing MyBehavior
editor.remove_behavior(MyBehavior)          # Returns the removed instance
editor.get_behavior(MyBehavior)             # Returns the instance or None
```

### Reacting to Option Changes

Every option except `"language"` and `"font"` always has a value, so a behavior can read a
setting from `self.options` when it needs it. For a setting that needs work when it changes,
register a handler. Handlers are called with the option's value right away, and again
whenever it changes. The handlers of `"language"` and `"font"` wait until they are set:

```python
class MyBehavior(Behavior):
    def __init__(self, editor):
        super().__init__(editor)
        self.font = QtGui.QFont()  # The default until the option is set
        self.watch_options({"font": self.set_font})

    def set_font(self, font):
        self.font = font
```

Parsing and highlighting are the expensive part of an editor, so the editor only sets its
language when it is first shown. Call `editor.load()` to set it for an editor you don't show.

### Keys, Painting and Signals

- Override `handle_key_press(event)` to get key presses before the editor's own key
  handling, and return `True` from it to consume the key. Behaviors with a higher
  `KEY_PRIORITY` get the keys first, like `TabCompletion`, so Tab accepts a completion
  before `SmartIndent` indents.
- Return actions from `get_hotkeys` to add keyboard shortcuts to the editor.
- Connect to `editor.behaviorPaint(event, painter)` to paint over the text.
- Connect to `editor.cursors.changed`, `editor.tree_manager.reparsed`, or
  `editor.undoRedoFinished` to react to the editor.
- Subclass `GutterWidget` (in `gutters.py`) for a column beside the text, like line numbers.

### Languages

Language-specific knowledge (comment prefix, indent rules, foldable node types, and the
highlight and identifier queries) lives in a `LanguageSpec`, looked up from the editor's
tree-sitter language. Add a language by registering a spec for its grammar name:

```python
from QCodeSitter.languages import LanguageSpec, register_language

register_language(LanguageSpec("lua", comment_prefix="-- "))
```

## Built-in Behaviors

| Behavior | Description |
|---|---|
| `SyntaxHighlighting` |  Tree-sitter-based syntax highlighting with incremental updates |
| `SmartIndent` |  Language-aware auto-indentation on Enter, Tab, Backspace |
| `LineNumbers` | Line number gutter |
| `AutoBracket` | Auto-close brackets, quotes, and parens; selection wrapping |
| `TabCompletion` | Autocomplete popup with pluggable providers |
| `CodeFolding` | Tree-sitter-based code folding with gutter indicators |
| `CommentToggle` | Toggle line comments (Ctrl+/) with language detection |
| `HighlightMatchingBrackets` | Highlight matching bracket/paren/brace pairs |
| `HighlightMatchingSelection` | Highlight all occurrences of selected text |
| `MultiCursorPaint` | Render primary and secondary cursors |
| `Overscroll` | Allow scrolling past end of document |

## Multi-Cursor Editing

The editor has built-in multi-cursor support. All text operations (insert, delete, indent, comment, etc.) apply to every cursor simultaneously.

**Default bindings:**
- **Ctrl+D** -- Select next occurrence of current selection
- **Ctrl+Alt+Up/Down** -- Add cursor above/below
- **Ctrl+Shift+L** -- Add cursors to all line ends in selection
- **Alt+Click** -- Add cursor at mouse position
- **Escape** -- Exit multi-cursor mode

Behaviors that modify text across multiple cursors use the editor's `CursorIterator`.
It moves one cursor to each cursor in turn, and shifts the later cursors by however much
each edit changed the document:

```python
def my_multi_cursor_operation(self):
    citer = self.editor.citer
    with self.editor.edit_session():  # One undo step, and one reparse
        for cursor in citer.iterate_cursors():
            cursor.insertText("hello")
            citer.mark_cursor_completed()
```

Marking a cursor completed stops later key handlers in the same edit session from editing it.

## Tree-Sitter Integration

QCodeSitter uses tree-sitter for parsing, with UTF-16 encoding throughout to match Qt's internal string representation. The `TreeManager` provides:

- Incremental parsing (only re-parses changed regions)
- A `reparsed` signal for loose coupling between components
- Pause/unpause to batch edits (e.g., during multi-cursor operations)

The `TrackedDocument` (a `QTextDocument` subclass) and `TrackedCursor` (a `QTextCursor` subclass) automatically track UTF-16 byte offsets and emit change signals that keep the parse tree in sync.

### Dependencies

- Python 3.10+

- [Qt.py](https://github.com/mottosso/Qt.py), and a Qt binding for it: PySide2, PySide6,
  PyQt5, or PyQt6. `pip install QCodeSitter[pyside6]` installs PySide6
- [tree-sitter](https://github.com/tree-sitter/py-tree-sitter)
- A tree-sitter language grammar (e.g., `tree-sitter-python`)

### Running Tests

Tests are set up to be run with `tox`. `python examples/demo.py` opens a window with the
default editor.

