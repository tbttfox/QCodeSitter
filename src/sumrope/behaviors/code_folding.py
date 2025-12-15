from __future__ import annotations
from . import HasResize, Behavior
from typing import TYPE_CHECKING
from Qt import QtGui, QtCore, QtWidgets
from Qt.QtCore import QObject
from tree_sitter import Node

if TYPE_CHECKING:
    from ..line_editor import CodeEditor


class FoldableRegion:
    """Represents a foldable code region"""

    def __init__(
        self, start_line: int, end_line: int, node: Node, hide_last_line: bool = True
    ):
        self.start_line = start_line  # 0-indexed
        self.end_line = end_line  # 0-indexed
        self.node = node
        self.is_folded = False
        self.hide_last_line = hide_last_line  # Whether to hide the closing line

    def contains_line(self, line: int) -> bool:
        """Check if this region contains the given line"""
        return self.start_line <= line <= self.end_line


class FoldingGutterArea(QtWidgets.QWidget):
    """Widget that displays fold indicators in the gutter"""

    def __init__(self, editor: CodeEditor, fg: QtGui.QColor, bg: QtGui.QColor):
        super().__init__(editor)
        self.editor: CodeEditor = editor
        self.fg_color = fg
        self.bg_color = bg
        self.regions: list[FoldableRegion] = []

        # Size of the fold icon (smaller for less width)
        self.icon_size = 9
        self.padding = 2

        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_area)
        self.update_width()

    def setColors(self, fg: QtGui.QColor, bg: QtGui.QColor):
        self.fg_color = fg
        self.bg_color = bg
        self.update()

    def sizeHint(self):
        return QtCore.QSize(self.width_hint(), 0)

    def width_hint(self):
        """Calculate width needed for fold indicators"""
        return self.icon_size + self.padding * 2

    def update_width(self):
        """Update the viewport margin to make room for fold indicators"""
        # This will be called by the behavior to set proper margin
        pass

    def update_area(self, rect: QtCore.QRect, dy: int):
        """Update the fold area when editor is scrolled or updated"""
        if dy:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())

    def set_regions(self, regions: list[FoldableRegion]):
        """Update the list of foldable regions"""
        self.regions = regions
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
        for region in self.regions:
            if region.start_line == line:
                return region
        return None

    def _draw_fold_indicator(
        self, painter: QtGui.QPainter, top: float, region: FoldableRegion
    ):
        """Draw a fold indicator (triangle or chevron)"""
        center_x = self.width() // 2
        center_y = int(top + self.editor.fontMetrics().height() // 2)
        size = self.icon_size // 2

        painter.setPen(QtGui.QPen(self.fg_color, 1.5))
        painter.setBrush(QtCore.Qt.NoBrush)

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
        if event.button() == QtCore.Qt.LeftButton:
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

        # Process all blocks up to (and possibly including) the last line
        block = start_block
        while block.isValid() and block.blockNumber() <= end_line:
            block.setVisible(not region.is_folded)
            block = block.next()

        # Update the editor viewport
        self.editor.viewport().update()
        self.editor.updateRequest.emit(self.editor.viewport().rect(), 0)


class CodeFolding(QObject, HasResize, Behavior):
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

    def __init__(self, editor: CodeEditor):
        QObject.__init__(self)
        Behavior.__init__(self, editor)
        self.setListen({"font", "colors"})

        # Colors for fold indicators
        self.fold_line_bg_color = QtGui.QColor(
            60, 60, 60, 80
        )  # Subtle background for folded lines
        self.fold_ellipsis_bg_color = QtGui.QColor(
            70, 70, 70, 150
        )  # Background box for ellipsis
        self.fold_ellipsis_fg_color = QtGui.QColor(
            120, 120, 120, 200
        )  # Ellipsis text color

        # Create the folding gutter area
        self.folding_area: FoldingGutterArea = FoldingGutterArea(
            self.editor,
            QtGui.QColor(150, 150, 150),  # temp default
            QtGui.QColor(40, 40, 40),  # temp default
        )

        # Connect to tree updates
        if self.editor.tree_manager.tree is not None:
            self._update_foldable_regions()
        self.editor.textChanged.connect(self._update_foldable_regions)

        # Connect to block count changes to update margins
        self.editor.blockCountChanged.connect(self.set_geometry)

        # Install event filter to draw fold indicators in the editor
        self.editor.viewport().installEventFilter(self)

        if editor.isVisible() and not self.folding_area.isVisible():
            self.folding_area.setVisible(True)

        self.set_geometry()
        self.updateAll()

    def eventFilter(self, obj, event):
        """Event filter to draw ellipsis on folded lines"""
        try:
            if obj == self.editor.viewport() and event.type() == QtCore.QEvent.Paint:
                # Let the normal painting happen first
                result = super().eventFilter(obj, event)
                # Then draw our fold indicators
                self._draw_fold_ellipsis()
                return result
        except RuntimeError:
            # Editor has been deleted during shutdown
            return False
        return super().eventFilter(obj, event)

    def _draw_fold_ellipsis(self):
        """Draw ellipsis indicators and background for folded lines"""
        painter = QtGui.QPainter(self.editor.viewport())
        painter.setFont(self.editor.font())

        # Find all folded regions
        for region in self.folding_area.regions:
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

            # Calculate line count
            num_hidden = region.end_line - region.start_line
            if region.hide_last_line:
                num_hidden += 1
            else:
                num_hidden -= 1

            # Draw ellipsis and line count
            ellipsis_text = "..."
            count_text = f" ({num_hidden} lines)" if num_hidden > 0 else ""
            full_text = ellipsis_text + count_text

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

    def _update_foldable_regions(self):
        """Scan the tree-sitter AST to find foldable regions"""
        if self.editor.tree_manager.tree is None:
            self.folding_area.set_regions([])
            return

        regions = []
        root_node = self.editor.tree_manager.tree.root_node

        # Recursively find foldable nodes
        self._find_foldable_nodes(root_node, regions)

        # Sort regions by start line
        regions.sort(key=lambda r: r.start_line)

        self.folding_area.set_regions(regions)

    def _find_foldable_nodes(self, node: Node, regions: list[FoldableRegion]):
        """Recursively find foldable nodes in the AST"""
        # Check if this node is foldable
        if node.type in self.HIDE_LAST_LINE_TYPES | self.KEEP_LAST_LINE_TYPES:
            # Only fold if the node spans multiple lines
            start_line = node.start_point.row
            end_line = node.end_point.row

            if end_line > start_line:
                # Determine if last line should be hidden based on node type
                hide_last = node.type in self.HIDE_LAST_LINE_TYPES
                regions.append(FoldableRegion(start_line, end_line, node, hide_last))

        # Recurse into children
        for child in node.children:
            self._find_foldable_nodes(child, regions)

    def _font(self, newfont):
        self.folding_area.setFont(newfont)

    font = property(None, _font)

    def _colors(self, val):
        self.folding_area.setColors(
            QtGui.QColor(val["gutter_fg"]), QtGui.QColor(val["gutter"])
        )

        # Subtle background for folded lines
        self.fold_line_bg_color = QtGui.QColor(val["bg_dim"])
        # Background box for ellipsis
        self.fold_ellipsis_bg_color = QtGui.QColor(val["hl_dim"])
        # Ellipsis text color
        self.fold_ellipsis_fg_color = QtGui.QColor(val["fg_dim"])

    colors = property(None, _colors)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        self.set_geometry()

    def set_geometry(self):
        """Handle resize events to update folding area geometry"""
        cr = self.editor.contentsRect()

        # Get the line number area width if it exists
        line_number_width = 0
        from .line_numbers import LineNumber

        line_number_behavior = self.editor.getBehavior(LineNumber)
        if line_number_behavior is not None:
            line_number_width = (
                line_number_behavior.line_number_area.line_number_area_width()
            )
            # Update line numbers to recalculate margin with folding width
            line_number_behavior.line_number_area.update_line_number_area_width()

        # Position folding area to the right of line numbers
        fold_width = self.folding_area.width_hint()
        self.folding_area.setGeometry(
            QtCore.QRect(
                cr.left() + line_number_width,
                cr.top(),
                fold_width,
                cr.height(),
            )
        )

    def remove(self):
        """Clean up when behavior is removed"""
        # Remove event filter
        self.editor.viewport().removeEventFilter(self)

        # Restore all folded regions
        for region in self.folding_area.regions:
            if region.is_folded:
                region.is_folded = False
                self.folding_area._apply_folding(region)

        # Trigger line numbers to update viewport margins without folding width
        from .line_numbers import LineNumber

        line_number_behavior = self.editor.getBehavior(LineNumber)
        if line_number_behavior is not None:
            line_number_behavior.line_number_area.update_line_number_area_width()
        else:
            self.editor.setViewportMargins(0, 0, 0, 0)

        self.folding_area.deleteLater()
        self.folding_area = None  # type: ignore
