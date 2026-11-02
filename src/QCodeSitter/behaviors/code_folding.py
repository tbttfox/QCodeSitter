from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from Qt import QtCore, QtGui, QtWidgets
from tree_sitter import Node, Tree

from ..gui_colors import GuiColors, gui_color
from ..gutters import GutterWidget
from ..languages import foldable_query, language_spec
from ..queries import query_byte_range
from ..utils import event_pos, make_shortcut_action
from . import Behavior

if TYPE_CHECKING:
    from ..code_editor import CodeEditor


@dataclass(eq=False)
class FoldableRegion:
    """A range of lines that can be folded under its first line

    Regions compare by identity, because their fold state changes
    """

    start_line: int  # 0-indexed
    end_line: int  # 0-indexed
    # The folded tree-sitter node, or None for a fold the user made
    node: Node | None = None
    hide_last_line: bool = True
    depth: int = 0  # Nesting depth (0 = top level)
    # Cursors on the first and last lines of a fold the user made. Qt moves
    # them with the text, so the fold follows its lines when lines above change
    anchors: tuple[QtGui.QTextCursor, QtGui.QTextCursor] | None = None
    is_folded: bool = field(default=False, init=False)

    @property
    def is_manual(self) -> bool:
        return self.node is None

    @property
    def hidden_end(self) -> int:
        """The last line that folding this region hides"""
        return self.end_line if self.hide_last_line else self.end_line - 1

    @property
    def num_hidden(self) -> int:
        return self.hidden_end - self.start_line

    def hides_line(self, line: int) -> bool:
        return self.is_folded and self.start_line < line <= self.hidden_end

    def follow_anchors(self) -> bool:
        """Move a manual fold to the lines its anchors are on now

        Returns whether it still spans more than one line
        """
        if self.anchors is not None:
            self.start_line, self.end_line = (c.blockNumber() for c in self.anchors)
        return self.end_line > self.start_line

    def state_key(self) -> tuple[str, int, int] | None:
        """Identifies the same tree-sitter region across reparses"""
        if self.node is None:
            return None
        return (self.node.type, self.start_line, self.end_line)


class FoldingGutterArea(GutterWidget):
    """The gutter column that shows fold indicators and toggles them on click"""

    regionClicked = QtCore.Signal(object)
    ICON_SIZE = 9
    PADDING = 2

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        # The outermost region starting on each line
        self.region_starts: dict[int, FoldableRegion] = {}

    def width_hint(self) -> int:
        return self.ICON_SIZE + 4 * self.PADDING

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), self.bg_color)
        painter.setPen(QtGui.QPen(self.fg_color, 1.5))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for block, top, bottom in self.visible_blocks(event.rect().bottom()):
            region = self.region_starts.get(block.blockNumber())
            if region is not None and bottom >= event.rect().top():
                self._draw_fold_indicator(painter, top, region.is_folded)

    def _draw_fold_indicator(
        self, painter: QtGui.QPainter, top: float, folded: bool
    ) -> None:
        """Draw a right-pointing triangle when folded, or a down-pointing one"""
        cx = self.width() // 2
        cy = int(top + self.editor.fontMetrics().height() // 2)
        size = self.ICON_SIZE // 2
        half = size // 2
        if folded:
            corners = [(cx - half, cy - size), (cx + half, cy), (cx - half, cy + size)]
        else:
            corners = [(cx - size, cy - half), (cx, cy + half), (cx + size, cy - half)]
        painter.drawPolygon([QtCore.QPoint(x, y) for x, y in corners])

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            click_y = event_pos(event).y()
            for block, top, bottom in self.visible_blocks(click_y):
                if top <= click_y < bottom:
                    region = self.region_starts.get(block.blockNumber())
                    if region is not None:
                        self.regionClicked.emit(region)
                    break
        super().mousePressEvent(event)


class CodeFolding(Behavior):
    """Fold the multi-line nodes of the tree-sitter tree, and manual selections

    The foldable node types come from the editor language's LanguageSpec
    """

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        # Every region, sorted by start line with parents before their children
        self.regions: list[FoldableRegion] = []

        self.fold_line_bg_color = QtGui.QColor()
        self.fold_ellipsis_bg_color = QtGui.QColor()
        self.fold_ellipsis_fg_color = QtGui.QColor()

        self.folding_area = FoldingGutterArea(self.editor)
        self.folding_area.regionClicked.connect(self.toggle_fold)
        self.watch_options(
            {"font": self.folding_area.setFont, "colors": self._set_colors}
        )

        if self.editor.tree_manager.tree is not None:
            self._update_foldable_regions()
        self.connect(self.editor.tree_manager.reparsed, self._update_foldable_regions)
        self.connect(
            self.editor.behaviorPaint,
            self.paint_folded_lines,
            QtCore.Qt.ConnectionType.DirectConnection,
        )

    def _set_colors(self, colors: GuiColors) -> None:
        self.folding_area.set_gutter_colors(
            gui_color(colors, "gutter_fg"), gui_color(colors, "gutter")
        )
        self.fold_line_bg_color = gui_color(colors, "bg_dim")
        self.fold_ellipsis_bg_color = gui_color(colors, "hl_dim")
        self.fold_ellipsis_fg_color = gui_color(colors, "fg_dim")

    # ------------------------------------------------------------------
    # Regions
    # ------------------------------------------------------------------

    def _set_regions(self, regions: list[FoldableRegion]) -> None:
        # The sort is stable, so parents stay before their children
        regions.sort(key=lambda r: r.start_line)
        self.regions = regions
        starts: dict[int, FoldableRegion] = {}
        for region in regions:
            # A fold the user made wins over the tree's region on the same line
            if region.is_manual or region.start_line not in starts:
                starts[region.start_line] = region
        self.folding_area.region_starts = starts
        self.folding_area.update()

    def _update_foldable_regions(self) -> None:
        """Rebuild the regions from the tree, keeping folded regions folded"""
        tree = self.editor.tree_manager.tree
        if tree is None:
            self._set_regions([])
            return

        folded = [r for r in self.regions if r.is_folded]
        folded_keys = {r.state_key() for r in folded}
        regions = self._find_foldable_regions(tree)
        restored = 0
        for region in regions:
            if region.state_key() in folded_keys:
                region.is_folded = True
                restored += 1
        manual = [r for r in folded if r.is_manual and r.follow_anchors()]
        self._set_regions(regions + manual)

        # A folded region that moved or changed can't be matched up, so it unfolds.
        # Its lines may have moved too, so recompute what is hidden from scratch
        if restored + len(manual) < len(folded):
            self._sync_block_visibility()
        elif folded:
            for region in self.regions:
                if region.is_folded:
                    self._apply_region(region)
            self._relayout()

    def _find_foldable_regions(self, tree: Tree) -> list[FoldableRegion]:
        """Find the foldable regions in the tree

        This runs on every reparse, so use a query instead of walking
        the whole tree in python
        """
        query = foldable_query(tree.language)
        if query is None:
            return []
        root = tree.root_node
        captures = query_byte_range(query, root, 0, root.end_byte)
        # Nodes in document order, with parents before their children
        nodes = sorted(
            captures.get("fold", []), key=lambda n: (n.start_byte, -n.end_byte)
        )

        hide_last_types = language_spec(tree.language).fold_hide_last_line
        # The end bytes of the foldable nodes that contain the current node
        # The depth counts single line nodes too
        parent_ends: list[int] = []
        regions = []
        for node in nodes:
            while parent_ends and parent_ends[-1] <= node.start_byte:
                parent_ends.pop()
            depth = len(parent_ends)
            parent_ends.append(node.end_byte)

            start_line = node.start_point.row
            end_line = node.end_point.row
            if end_line > start_line:
                hide_last = node.type in hide_last_types
                regions.append(
                    FoldableRegion(start_line, end_line, node, hide_last, depth)
                )
        return regions

    # ------------------------------------------------------------------
    # Folding
    # ------------------------------------------------------------------

    def _hidden_by_other(self, line: int, region: FoldableRegion) -> bool:
        return any(r.hides_line(line) for r in self.regions if r is not region)

    def _apply_region(self, region: FoldableRegion) -> None:
        """Show or hide the lines of a region to match its fold state

        Unfolding keeps the lines of nested folded regions hidden
        """
        block = self.editor.document().findBlockByNumber(region.start_line + 1)
        while block.isValid() and block.blockNumber() <= region.hidden_end:
            line = block.blockNumber()
            block.setVisible(
                not region.is_folded and not self._hidden_by_other(line, region)
            )
            block = block.next()

    def _sync_block_visibility(self) -> None:
        """Show or hide every line to match all the fold states"""
        block = self.editor.document().firstBlock()
        while block.isValid():
            line = block.blockNumber()
            block.setVisible(not any(r.hides_line(line) for r in self.regions))
            block = block.next()
        self._relayout()

    def _relayout(self) -> None:
        """Repaint the text and the gutters after lines were shown or hidden"""
        self.editor.viewport().update()
        self.editor.gutters.update()

    def set_folded(self, region: FoldableRegion, folded: bool) -> None:
        if region.is_folded != folded:
            region.is_folded = folded
            self._apply_region(region)
            self._relayout()

    def toggle_fold(self, region: FoldableRegion) -> None:
        self.set_folded(region, not region.is_folded)

    def _set_all_folded(
        self, should_fold: Callable[[FoldableRegion], bool | None]
    ) -> None:
        """Fold or unfold every region

        Args:
            should_fold: Whether to fold a region, or None to leave it as is
        """
        for region in self.regions:
            fold = should_fold(region)
            if fold is not None and region.is_folded != fold:
                region.is_folded = fold
                self._apply_region(region)
        self._relayout()

    def fold_to_level(self, min_depth: int) -> None:
        """Fold the regions at or deeper than a depth, and unfold the rest

        Args:
            min_depth: The depth to start folding at. 0 folds everything,
                1 keeps the top level unfolded, etc.
        """
        self._set_all_folded(lambda r: r.depth >= min_depth)

    def unfold_to_level(self, max_depth: int) -> None:
        """Unfold the regions up to and including a depth

        Args:
            max_depth: 0 unfolds the top level only, 1 unfolds the top
                and next level, etc.
        """
        self._set_all_folded(lambda r: False if r.depth <= max_depth else None)

    def fold_all(self) -> None:
        self._set_all_folded(lambda r: True)

    def unfold_all(self) -> None:
        self._set_all_folded(lambda r: False)

    def create_manual_fold(self) -> bool:
        """Fold the lines of the selection under its first line

        Returns whether a fold was made, which needs at least 2 selected lines
        """
        cursor = self.editor.textCursor()
        doc = self.editor.document()
        start_line = doc.findBlock(cursor.selectionStart()).blockNumber()
        end_line = doc.findBlock(cursor.selectionEnd()).blockNumber()
        if end_line <= start_line:
            return False

        anchors = (
            QtGui.QTextCursor(doc.findBlockByNumber(start_line)),
            QtGui.QTextCursor(doc.findBlockByNumber(end_line)),
        )
        # Manual folds keep their last line showing, like a closing bracket
        region = FoldableRegion(
            start_line, end_line, hide_last_line=False, anchors=anchors
        )
        self._set_regions([*self.regions, region])
        self.set_folded(region, True)
        return True

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint_folded_lines(
        self, _event: QtGui.QPaintEvent, painter: QtGui.QPainter
    ) -> None:
        """Shade each folded line, and say how many lines it hides"""
        metrics = self.editor.fontMetrics()
        doc = self.editor.document()
        width = self.editor.viewport().width()
        painter.save()
        try:
            painter.setFont(self.editor.font())
            painter.setPen(self.fold_ellipsis_fg_color)
            for region in self.regions:
                if not region.is_folded:
                    continue
                block = doc.findBlockByNumber(region.start_line)
                if not block.isValid() or not block.isVisible():
                    continue
                geom = self.editor.blockBoundingGeometry(block).translated(
                    self.editor.contentOffset()
                )
                top, height = int(geom.top()), int(geom.height())
                painter.fillRect(0, top, width, height, self.fold_line_bg_color)

                if region.num_hidden <= 0:
                    continue
                plural = "s" if region.num_hidden > 1 else ""
                text = f"... ({region.num_hidden} hidden line{plural})"
                x = metrics.horizontalAdvance(block.text() + " ")
                box_padding = 3
                painter.fillRect(
                    x - box_padding,
                    top,
                    metrics.horizontalAdvance(text) + box_padding * 2,
                    height,
                    self.fold_ellipsis_bg_color,
                )
                painter.drawText(x, int(geom.top() + metrics.ascent()), text)
        finally:
            painter.restore()

    def remove(self) -> None:
        super().remove()
        for region in self.regions:
            region.is_folded = False
        self._sync_block_visibility()
        self.folding_area.remove()

    def get_hotkeys(self) -> list[QtWidgets.QAction]:
        actions = [
            make_shortcut_action(
                self.editor, "Ctrl+Shift+[", self.fold_all, "Fold All"
            ),
            make_shortcut_action(
                self.editor, "Ctrl+Shift+]", self.unfold_all, "Unfold All"
            ),
            make_shortcut_action(
                self.editor,
                "Ctrl+Shift+.",
                self.create_manual_fold,
                "Create Manual Fold",
            ),
        ]
        for i in range(10):
            # triggered passes a `checked` bool, so take that before the level
            actions.append(
                make_shortcut_action(
                    self.editor,
                    f"Ctrl+{i}",
                    lambda _checked=False, level=i: self.fold_to_level(level),
                    f"Fold to Level {i}",
                )
            )
        return actions
