from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from Qt import QtCore, QtGui, QtWidgets
from tree_sitter import Language, Node, Query, Tree

from ..gutter_widget import GutterWidget
from ..ts_version_fix import query_byte_range
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


class FoldableRegion:
    """Represents a foldable code region"""

    def __init__(
        self,
        start_line: int,
        end_line: int,
        node: Node | None = None,
        hide_last_line: bool = True,
        depth: int = 0,
    ):
        self.start_line = start_line  # 0-indexed
        self.end_line = end_line  # 0-indexed
        self.node = node  # Optional: None for manual folds
        self.is_folded = False
        self.hide_last_line = hide_last_line  # Whether to hide the closing line
        self.depth = depth  # Nesting depth (0 = top level)
        self.is_manual = node is None  # True if this is a user-created fold

    def contains_line(self, line: int) -> bool:
        """Check if this region contains the given line"""
        return self.start_line <= line <= self.end_line


class FoldingGutterArea(GutterWidget):
    """Widget that displays fold indicators in the gutter"""

    def __init__(self, editor: CodeEditor, fg: QtGui.QColor, bg: QtGui.QColor):
        super().__init__("FoldArea", editor)
        self.fg_color = fg
        self.bg_color = bg

        self.fold_line_bg_color = QtGui.QColor(60, 60, 60, 80)
        self.fold_ellipsis_bg_color = QtGui.QColor(70, 70, 70, 150)
        self.fold_ellipsis_fg_color = QtGui.QColor(120, 120, 120, 200)

        self.regions: list[FoldableRegion] = []
        # The outermost region starting on each line, for painting and clicking
        self._region_starts: dict[int, FoldableRegion] = {}

        # Size of the fold icon (smaller for less width)
        self.icon_size = 9
        self.padding = 2

        # Install event filter to draw fold indicators in the editor
        self.editor.viewport().installEventFilter(self)

        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_gutter)
        self.update_width()

    def setColors(self, fg: QtGui.QColor, bg: QtGui.QColor):
        self.fg_color = fg
        self.bg_color = bg

    def width_hint(self):
        digits = len(str(max(1, self.editor.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def set_regions(self, regions: list[FoldableRegion]):
        """Update the list of foldable regions, sorted by start line"""
        self.regions = regions
        self._region_starts = {}
        for region in regions:
            self._region_starts.setdefault(region.start_line, region)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        """Paint fold indicators"""
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), self.bg_color)

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = (
            self.editor.blockBoundingGeometry(block)
            .translated(self.editor.contentOffset())
            .top()
        )
        bottom = top + self.editor.blockBoundingRect(block).height()

        # Draw fold indicators for each visible block
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # Check if this line starts a foldable region
                region = self._get_region_starting_at(block_number)
                if region is not None:
                    self._draw_fold_indicator(painter, top, region)

            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1

    def _get_region_starting_at(self, line: int) -> FoldableRegion | None:
        """Get the foldable region that starts at the given line"""
        return self._region_starts.get(line)

    def _draw_fold_indicator(
        self, painter: QtGui.QPainter, top: float, region: FoldableRegion
    ):
        """Draw a fold indicator (triangle or chevron)"""
        center_x = self.width() // 2
        center_y = int(top + self.editor.fontMetrics().height() // 2)
        size = self.icon_size // 2

        painter.setPen(QtGui.QPen(self.fg_color, 1.5))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

        if region.is_folded:
            # Draw right-pointing triangle (folded state)
            points = [
                QtCore.QPoint(center_x - size // 2, center_y - size),
                QtCore.QPoint(center_x + size // 2, center_y),
                QtCore.QPoint(center_x - size // 2, center_y + size),
            ]
        else:
            # Draw down-pointing triangle (expanded state)
            points = [
                QtCore.QPoint(center_x - size, center_y - size // 2),
                QtCore.QPoint(center_x, center_y + size // 2),
                QtCore.QPoint(center_x + size, center_y - size // 2),
            ]

        painter.drawPolygon(points)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle clicks on fold indicators"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Determine which line was clicked
            block = self.editor.firstVisibleBlock()
            top = (
                self.editor.blockBoundingGeometry(block)
                .translated(self.editor.contentOffset())
                .top()
            )
            bottom = top + self.editor.blockBoundingRect(block).height()
            click_y = event.pos().y()

            while block.isValid():
                if top <= click_y < bottom:
                    line_number = block.blockNumber()
                    region = self._get_region_starting_at(line_number)
                    if region is not None:
                        # Toggle fold state
                        region.is_folded = not region.is_folded
                        self._apply_folding(region)
                        self.update()
                    break

                block = block.next()
                top = bottom
                bottom = top + self.editor.blockBoundingRect(block).height()

        super().mousePressEvent(event)

    def _apply_folding(self, region: FoldableRegion):
        """Apply or remove folding for a region"""
        # Hide/show blocks in the region
        # Start from the line after the opening line
        start_block = self.editor.document().findBlockByNumber(region.start_line + 1)

        # Determine the end line based on hide_last_line setting
        end_line = region.end_line if region.hide_last_line else region.end_line - 1

        if region.is_folded:
            # Folding: hide all blocks unconditionally
            block = start_block
            while block.isValid() and block.blockNumber() <= end_line:
                block.setVisible(False)
                block = block.next()
        else:
            # Unfolding: only show blocks that aren't hidden by nested folds
            block = start_block
            while block.isValid() and block.blockNumber() <= end_line:
                line_num = block.blockNumber()
                # Check if this line is hidden by a nested folded region
                should_be_visible = not self._is_line_in_folded_region(line_num, region)
                block.setVisible(should_be_visible)
                block = block.next()

        # Update the editor viewport
        self.editor.viewport().update()
        self.editor.updateRequest.emit(self.editor.viewport().rect(), 0)

    def _is_line_in_folded_region(
        self, line: int, exclude_region: FoldableRegion
    ) -> bool:
        """Check if a line is inside a folded region (excluding the specified region)"""
        for region in self.regions:
            if region == exclude_region:
                continue
            if region.is_folded and region.start_line < line <= region.end_line:
                return True
        return False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Event filter to draw ellipsis on folded lines"""
        try:
            if (
                watched == self.editor.viewport()
                and event.type() == QtCore.QEvent.Type.Paint
            ):
                # Let the normal painting happen first
                result = super().eventFilter(watched, event)
                # Then draw our fold indicators
                self._draw_fold_ellipsis()
                return result
        except RuntimeError:
            # Editor has been deleted during shutdown
            return False
        return super().eventFilter(watched, event)

    def _draw_fold_ellipsis(self):
        """Draw ellipsis indicators and background for folded lines"""
        painter = QtGui.QPainter(self.editor.viewport())
        painter.setFont(self.editor.font())

        # Find all folded regions
        for region in self.regions:
            if not region.is_folded:
                continue

            # Get the block for the start line
            block = self.editor.document().findBlockByNumber(region.start_line)
            if not block.isValid() or not block.isVisible():
                continue

            # Calculate the position for the ellipsis
            block_geom = self.editor.blockBoundingGeometry(block).translated(
                self.editor.contentOffset()
            )
            block_text = block.text()

            # Draw subtle background across the entire line
            painter.fillRect(
                0,
                int(block_geom.top()),
                self.editor.viewport().width(),
                int(block_geom.height()),
                self.fold_line_bg_color,
            )

            # Position at the end of the text
            text_width = self.editor.fontMetrics().horizontalAdvance(block_text)
            ellipsis_x = text_width + self.editor.fontMetrics().horizontalAdvance(" ")
            ellipsis_y = int(block_geom.top() + self.editor.fontMetrics().ascent())

            # The lines after the start line are hidden, maybe excluding the last one
            num_hidden = region.end_line - region.start_line
            if not region.hide_last_line:
                num_hidden -= 1
            plural = "s" if num_hidden > 1 else ""

            # Draw ellipsis and line count
            full_text = (
                f"... ({num_hidden} hidden line{plural})" if num_hidden > 0 else ""
            )

            # Draw the ellipsis and count with a darker background box
            box_padding = 3
            full_width = self.editor.fontMetrics().horizontalAdvance(full_text)
            painter.fillRect(
                int(ellipsis_x - box_padding),
                int(block_geom.top()),
                full_width + box_padding * 2,
                int(block_geom.height()),
                self.fold_ellipsis_bg_color,
            )

            # Draw the text
            painter.setPen(self.fold_ellipsis_fg_color)
            painter.drawText(int(ellipsis_x), ellipsis_y, full_text)


class CodeFolding(Behavior):
    """Behavior that provides code folding based on tree-sitter AST"""

    # Node types where the last line should be hidden (Python indentation-based blocks)
    HIDE_LAST_LINE_TYPES = {
        "class_definition",
        "for_statement",
        "function_definition",
        "if_statement",
        "match_statement",
        "try_statement",
        "while_statement",
        "with_statement",
    }

    # Node types where the last line should stay visible (explicit delimiters)
    KEEP_LAST_LINE_TYPES = {
        "argument_list",
        "dictionary",
        "list",
        "tuple",
    }

    FOLDABLE_TYPES = HIDE_LAST_LINE_TYPES | KEEP_LAST_LINE_TYPES

    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.setListen({"font", "colors"})
        self._query: Query | None = None
        self._query_language: Language | None = None

        # Colors for fold indicators
        # Subtle background for folded lines
        # Create the folding gutter area
        self.folding_area: FoldingGutterArea = FoldingGutterArea(
            self.editor,
            QtGui.QColor(150, 150, 150),  # temp default
            QtGui.QColor(40, 40, 40),  # temp default
        )

        # Connect to tree updates
        if self.editor.tree_manager.tree is not None:
            self._update_foldable_regions()
        self.editor.tree_manager.reparsed.connect(self._update_foldable_regions)

        if editor.isVisible() and not self.folding_area.isVisible():
            self.folding_area.setVisible(True)

        self.folding_area.set_gutter_geo()
        self.updateAll()

    def _update_foldable_regions(self):
        """Scan the tree-sitter AST to find foldable regions"""
        if self.editor.tree_manager.tree is None:
            self.folding_area.set_regions([])
            return

        # Save existing fold states
        # For AST-based folds: use (node_type, start_line, end_line)
        # For manual folds: preserve them separately
        old_fold_states = {}
        manual_folds = []
        for region in self.folding_area.regions:
            if region.is_folded:
                if region.is_manual:
                    # Preserve manual folds as-is
                    manual_folds.append(region)
                elif region.node is not None:
                    # Save AST-based fold state
                    key = (region.node.type, region.start_line, region.end_line)
                    old_fold_states[key] = True

        regions = self._find_foldable_regions(self.editor.tree_manager.tree)

        # Restore fold states for matching AST nodes
        for region in regions:
            if region.node is not None:
                key = (region.node.type, region.start_line, region.end_line)
                if key in old_fold_states:
                    region.is_folded = True
                    # Re-apply the folding to ensure blocks are hidden
                    self.folding_area._apply_folding(region)

        # Add back manual folds
        regions.extend(manual_folds)

        # Sort regions by start line. The sort is stable, so parents stay first
        regions.sort(key=lambda r: r.start_line)

        self.folding_area.set_regions(regions)

    def _foldable_query(self, language: Language) -> Query | None:
        """Build a query that captures every foldable node type in the language"""
        if language != self._query_language:
            self._query_language = language
            types = [
                t
                for t in sorted(self.FOLDABLE_TYPES)
                if language.id_for_node_kind(t, True)
            ]
            source = "[{}] @fold".format(" ".join(f"({t})" for t in types))
            self._query = Query(language, source) if types else None
        return self._query

    def _find_foldable_regions(self, tree: Tree) -> list[FoldableRegion]:
        """Find the foldable regions in the AST

        This runs on every reparse, so use a query instead of walking
        the whole tree in python
        """
        query = self._foldable_query(tree.language)
        if query is None:
            return []
        root = tree.root_node
        captures = query_byte_range(query, root, 0, root.end_byte)
        if not captures:
            return []

        # Nodes in document order, with parents before their children
        nodes = sorted(captures["fold"], key=lambda n: (n.start_byte, -n.end_byte))

        # The end bytes of the foldable nodes that contain the current node
        # The depth counts single line nodes too
        parent_ends: list[int] = []
        regions = []
        for node in nodes:
            while parent_ends and parent_ends[-1] <= node.start_byte:
                parent_ends.pop()
            depth = len(parent_ends)
            parent_ends.append(node.end_byte)

            # Only fold if the node spans multiple lines
            start_line = node.start_point.row
            end_line = node.end_point.row
            if end_line > start_line:
                hide_last = node.type in self.HIDE_LAST_LINE_TYPES
                regions.append(
                    FoldableRegion(start_line, end_line, node, hide_last, depth)
                )
        return regions

    def _set_folded(self, should_fold: Callable[[FoldableRegion], bool | None]):
        """Fold or unfold every region

        Args:
            should_fold: Whether to fold a region, or None to leave it as is
        """
        for region in self.folding_area.regions:
            fold = should_fold(region)
            if fold is not None and region.is_folded != fold:
                region.is_folded = fold
                self.folding_area._apply_folding(region)

        self.folding_area.update()
        self.editor.viewport().update()

    def fold_to_level(self, max_depth: int):
        """Fold all regions at or deeper than the specified depth level

        Args:
            max_depth: Maximum depth to keep unfolded (0 = fold everything, 1 = keep top level visible, etc.)
        """
        self._set_folded(lambda r: r.depth >= max_depth)

    def unfold_to_level(self, max_depth: int):
        """Unfold all regions up to and including the specified depth level

        Args:
            max_depth: Maximum depth to unfold (0 = unfold top level only, 1 = unfold top and next level, etc.)
        """
        self._set_folded(lambda r: False if r.depth <= max_depth else None)

    def fold_all(self):
        """Fold all foldable regions"""
        self._set_folded(lambda r: True)

    def unfold_all(self):
        """Unfold all foldable regions"""
        self._set_folded(lambda r: False)

    def create_manual_fold(self):
        """Create a manual fold from the current selection

        Returns:
            bool: True if fold was created, False if no valid selection
        """
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return

        # Get selection block range
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()

        # Convert to line numbers
        doc = self.editor.document()
        start_block = doc.findBlock(selection_start)
        end_block = doc.findBlock(selection_end)

        start_line = start_block.blockNumber()
        end_line = end_block.blockNumber()

        # Need at least 2 lines to fold
        if end_line <= start_line:
            return

        # Check if this region overlaps with existing folds
        # We'll allow it but the user should be aware
        new_region = FoldableRegion(
            start_line=start_line,
            end_line=end_line,
            node=None,  # No AST node for manual folds
            hide_last_line=False,  # Don't hide the last line for manual folds
            depth=0,  # Manual folds are always depth 0
        )

        regions = [*self.folding_area.regions, new_region]
        regions.sort(key=lambda r: r.start_line)
        self.folding_area.set_regions(regions)

        # Immediately fold it
        new_region.is_folded = True
        self.folding_area._apply_folding(new_region)

        # Update display
        self.folding_area.update()
        self.editor.viewport().update()

    def _font(self, newfont):
        self.folding_area.setFont(newfont)

    font = property(None, _font)

    def _colors(self, val):
        self.folding_area.setColors(
            QtGui.QColor(val["gutter_fg"]), QtGui.QColor(val["gutter"])
        )

        self.folding_area.fold_line_bg_color = QtGui.QColor(val["bg_dim"])
        self.folding_area.fold_ellipsis_bg_color = QtGui.QColor(val["hl_dim"])
        self.folding_area.fold_ellipsis_fg_color = QtGui.QColor(val["fg_dim"])

    colors = property(None, _colors)

    def remove(self):
        """Clean up when behavior is removed"""
        super().remove()
        self.editor.tree_manager.reparsed.disconnect(self._update_foldable_regions)
        self.editor.viewport().removeEventFilter(self.folding_area)

        # Restore all folded regions
        for region in self.folding_area.regions:
            if region.is_folded:
                region.is_folded = False
                self.folding_area._apply_folding(region)

        self.folding_area.clear_width()
        self.folding_area.deleteLater()
        self.folding_area = None  # type: ignore

    def getHotkeys(self) -> list[QtWidgets.QAction]:
        """Return keyboard shortcut actions for code folding operations"""
        actions = []

        def _action(name, shortcut, method):
            action = QtWidgets.QAction(name, self.editor)
            action.setShortcut(QtGui.QKeySequence(shortcut))
            action.triggered.connect(method)
            actions.append(action)

        _action("Fold All", "Ctrl+Shift+[", self.fold_all)
        _action("Unfold All", "Ctrl+Shift+]", self.unfold_all)
        _action("Create Manual Fold", "Ctrl+Shift+.", self.create_manual_fold)

        for i in range(10):
            # triggered passes a `checked` bool, so take that before the level
            _action(
                f"Fold to Level {i}",
                f"Ctrl+{i}",
                lambda _checked=False, level=i: self.fold_to_level(level),
            )

        return actions
