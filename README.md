# QCodeSitter

A reusable, tree-sitter-powered code editor widget for Qt applications. QCodeSitter provides a `QPlainTextEdit` subclass with syntax highlighting, multi-cursor editing, smart indentation, code folding, and more -- all driven by a modular **Behavior** system that makes it easy to add, remove, or customize features.

This is not an IDE. It's a drop-in editor widget you can embed in your own Qt application.

## Quick Start

```python
from tree_sitter import Language
import tree_sitter_python as tspython
from Qt import QtWidgets, QtGui

from QCodeSitter import CodeEditor
from QCodeSitter.editor_options import EditorOptions
from QCodeSitter.hl_groups import FORMAT_SPECS, COLORS
from QCodeSitter.highlight_query import HIGHLIGHT_QUERY
from QCodeSitter.behaviors.syntax_highlighting import SyntaxHighlighting
from QCodeSitter.behaviors.smart_indent import SmartIndent
from QCodeSitter.behaviors.line_numbers import LineNumber
from QCodeSitter.behaviors.auto_bracket import AutoBracket

# Configure the editor
options = EditorOptions({
    "space_indent_width": 4,
    "indent_using_tabs": False,
    "language": Language(tspython.language()),
    "highlights": (HIGHLIGHT_QUERY, FORMAT_SPECS),
    "colors": COLORS,
    "font": QtGui.QFont("Consolas", pointSize=11),
})

# Create the editor and add the behaviors you want
editor = CodeEditor(options)
editor.addBehavior(SyntaxHighlighting)
editor.addBehavior(SmartIndent)
editor.addBehavior(LineNumber)
editor.addBehavior(AutoBracket)
```

You only pay for what you use. If you don't need code folding, don't add it. If you want custom behavior, write your own.

## The Behavior System

Every editor feature beyond basic text editing is implemented as a **Behavior**. Behaviors are modular, self-contained classes that plug into the editor through a well-defined interface.

### Base Class

All behaviors inherit from `Behavior`:

```python
from QCodeSitter.behaviors import Behavior

class MyBehavior(Behavior):
    def __init__(self, editor):
        super().__init__(editor)
        # self.editor  - the CodeEditor instance
        # self.options  - the EditorOptions dict-like object

    def remove(self):
        # Clean up when the behavior is removed
        pass
```

Behaviors are added and removed at runtime:

```python
old, new = editor.addBehavior(MyBehavior)   # Returns (old_instance, new_instance)
editor.removeBehavior(MyBehavior)            # Returns removed instance
editor.getBehavior(MyBehavior)               # Returns instance or None
```

### Mixin Interfaces

Behaviors declare their capabilities by mixing in one or more interfaces:

| Mixin | Method | Purpose |
|---|---|---|
| `HasKeyPress` | `keyPressEvent(event) -> bool` | Handle keyboard input (Tab, Enter, Backspace, etc.) |
| `HasHotkeys` | `getHotkeys() -> ShortcutSlotGroup` | Declare user-configurable shortcuts (Ctrl+/, Ctrl+D, etc.) |
| `HasPaint` | `paintEvent(event, painter) -> bool` | Custom rendering in the editor viewport |
| `HasResize` | `resizeEvent(event) -> bool` | React to editor resize |
| `HasUndoRedo` | `prepareUndo()`, `prepareRedo()`, `afterUndoRedo()` | Hook into undo/redo lifecycle |

For example, a behavior that handles both keyboard input and custom painting:

```python
from QCodeSitter.behaviors import Behavior, HasKeyPress, HasPaint

class MyFeature(HasKeyPress, HasPaint, Behavior):
    def keyPressEvent(self, event):
        # Return True to consume the event, False to pass it through
        if event.key() == Qt.Key_F1:
            self.do_something()
            return True
        return False

    def paintEvent(self, event, painter):
        # Draw custom overlays
        painter.drawRect(...)
        return False
```

### Reacting to Option Changes

Behaviors can listen for option changes:

```python
class MyBehavior(Behavior):
    def __init__(self, editor):
        super().__init__(editor)
        self.setListen({"colors", "font"})
        self.updateAll()  # Apply current values immediately
```

When a listened key changes in `EditorOptions`, the behavior's attribute of the same name is set automatically via `updateOptions`.

### HasHotkeys in Detail

`HasHotkeys` integrates with `QtShortcutManager` for user-configurable shortcuts. You define slots with default key bindings, and the system auto-binds methods by name:

```python
from QCodeSitter.behaviors import Behavior, HasHotkeys
from QtShortcutManager import ShortcutSlot, ShortcutSlotGroup

class CommentToggle(HasHotkeys, Behavior):
    def getHotkeys(self) -> ShortcutSlotGroup:
        slots = [
            ShortcutSlot(
                name="Toggle Comment",
                defaults=[QtGui.QKeySequence("Ctrl+/")],
                desc="Toggle line comment on current line or selection",
            )
        ]
        return ShortcutSlotGroup("Comment", slots=slots)

    def toggle_comment(self):
        # Slot name "Toggle Comment" auto-binds to method "toggle_comment"
        ...
```

Use `HasHotkeys` for modifier-key shortcuts (Ctrl+, Alt+, etc.) that should be user-configurable. Use `HasKeyPress` for intrinsic editing keys like Tab, Enter, and Backspace.

## Built-in Behaviors

| Behavior | Interfaces | Description |
|---|---|---|
| `SyntaxHighlighting` | `HasUndoRedo` | Tree-sitter-based syntax highlighting with incremental updates |
| `SmartIndent` | `HasKeyPress` | Language-aware auto-indentation on Enter, Tab, Backspace |
| `LineNumber` | `Behavior` | Line number gutter |
| `AutoBracket` | `HasKeyPress` | Auto-close brackets, quotes, and parens; selection wrapping |
| `TabCompletion` | `HasKeyPress` | Autocomplete popup with pluggable providers |
| `CodeFolding` | `HasHotkeys` | Tree-sitter-based code folding with gutter indicators |
| `CommentToggle` | `HasHotkeys` | Toggle line comments (Ctrl+/) with language detection |
| `HighlightMatchingBrackets` | `Behavior` | Highlight matching bracket/paren/brace pairs |
| `HighlightMatchingSelection` | `Behavior` | Highlight all occurrences of selected text |
| `MultiCursorPaint` | `HasPaint` | Render primary and secondary cursors |
| `Overscroll` | `HasPaint` | Allow scrolling past end of document |

## Multi-Cursor Editing

The editor has built-in multi-cursor support. All text operations (insert, delete, indent, comment, etc.) apply to every cursor simultaneously.

**Default bindings:**
- **Ctrl+D** -- Select next occurrence of current selection
- **Ctrl+Alt+Up/Down** -- Add cursor above/below
- **Ctrl+Shift+L** -- Add cursors to all line ends in selection
- **Alt+Click** -- Add cursor at mouse position
- **Escape** -- Exit multi-cursor mode

Behaviors that modify text across multiple cursors use `CursorIterator`, which handles position offset tracking as earlier cursors shift later ones:

```python
from QCodeSitter.code_editor import CursorIterator

def my_multi_cursor_operation(self):
    citer = CursorIterator(self.editor)
    self.editor.citer = citer
    for cursor in citer.iterate_cursors():
        # Modify text through cursor
        cursor.insertText("hello")
        citer.update_offset(len("hello"))
        citer.cursor_completed()
```

## Tree-Sitter Integration

QCodeSitter uses tree-sitter for parsing, with UTF-16 encoding throughout to match Qt's internal string representation. The `TreeManager` provides:

- Incremental parsing (only re-parses changed regions)
- A `reparsed` signal for loose coupling between components
- Pause/unpause to batch edits (e.g., during multi-cursor operations)

The `TrackedDocument` (a `QTextDocument` subclass) and `TrackedCursor` (a `QTextCursor` subclass) automatically track UTF-16 byte offsets and emit change signals that keep the parse tree in sync.

## Installation

```
pip install .
```

### Dependencies

- [Qt.py](https://github.com/mottosso/Qt.py) (works with PySide2, PySide6, PyQt5, or PyQt6)
- [tree-sitter](https://github.com/tree-sitter/py-tree-sitter)
- A tree-sitter language grammar (e.g., `tree-sitter-python`)

### Running Tests

```
pip install .[test]
pytest tests/ -v
```

Or with tox:

```
tox
```
