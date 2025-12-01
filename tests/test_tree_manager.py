import pytest
from tree_sitter import Language, Point
import tree_sitter_python as tspython
from sumrope.tree_manager import TreeManager


class TestTreeManager:
    """Tests for the TreeManager class"""

    @pytest.fixture
    def source_text(self):
        """Sample Python source code for testing"""
        return b"def foo():\n    pass\n"

    @pytest.fixture
    def source_callback(self, source_text):
        """Create a simple source callback for testing"""
        def callback(byte_offset: int, point: Point) -> bytes:
            return source_text[byte_offset:]
        return callback

    @pytest.fixture
    def tree_manager(self, source_callback):
        """Create a TreeManager instance for testing"""
        language = Language(tspython.language())
        return TreeManager(language, source_callback)

    def test_tree_manager_initialization(self, tree_manager):
        """Test that TreeManager initializes correctly"""
        assert tree_manager.parser is not None
        assert tree_manager.tree is None  # No tree until first update

    def test_tree_manager_first_update(self, tree_manager):
        """Test that the first update creates a parse tree"""
        # Perform first parse (no edit needed)
        tree_manager.update(
            start_byte=0,
            old_end_byte=0,
            new_end_byte=17,
            start_point=Point(0, 0),
            old_end_point=Point(0, 0),
            new_end_point=Point(2, 0)
        )

        assert tree_manager.tree is not None
        assert tree_manager.root_node is not None
        assert tree_manager.root_node.type == "module"

    def test_get_node_at_point(self, tree_manager):
        """Test node lookup at specific byte offsets"""
        # First create a tree
        tree_manager.update(
            start_byte=0,
            old_end_byte=0,
            new_end_byte=17,
            start_point=Point(0, 0),
            old_end_point=Point(0, 0),
            new_end_point=Point(2, 0)
        )

        # Get node at the 'd' in 'def'
        node = tree_manager.get_node_at_point(0)
        assert node is not None

        # Get node at the 'f' in 'foo'
        node = tree_manager.get_node_at_point(4)
        assert node is not None

    def test_get_node_at_point_no_tree(self, tree_manager):
        """Test that get_node_at_point returns None when no tree exists"""
        node = tree_manager.get_node_at_point(0)
        assert node is None

    def test_incremental_update(self, source_callback):
        """Test that incremental updates work correctly"""
        language = Language(tspython.language())

        # Create initial source
        initial_source = b"x = 1\n"
        callback = lambda byte_offset, point: initial_source[byte_offset:]
        tm = TreeManager(language, callback)

        # Initial parse
        tm.update(
            start_byte=0,
            old_end_byte=0,
            new_end_byte=len(initial_source),
            start_point=Point(0, 0),
            old_end_point=Point(0, 0),
            new_end_point=Point(1, 0)
        )

        assert tm.tree is not None
        old_tree = tm.tree

        # Modify source (change "x = 1" to "x = 2")
        modified_source = b"x = 2\n"
        callback = lambda byte_offset, point: modified_source[byte_offset:]
        tm._source_callback = callback

        # Incremental update
        tm.update(
            start_byte=4,
            old_end_byte=5,
            new_end_byte=5,
            start_point=Point(0, 4),
            old_end_point=Point(0, 5),
            new_end_point=Point(0, 5)
        )

        assert tm.tree is not None
        assert tm.tree is not old_tree  # Should be a new tree
