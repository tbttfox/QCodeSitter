"""The editor's cursors

- state: CursorState, a cursor's anchor and position
- multi: MultiCursor, the editor's cursors (`editor.cursors`) and their commands
- iterator: CursorIterator, which runs an edit at every cursor (`editor.citer`)
- tracked: TrackedCursor, a QTextCursor that reports its edits to the parse tree
"""
