import pytest
import jax.numpy as jnp

from snapshot_manager.snapshot_manager import SnapshotManager
from snapshot_manager.query import (
    AndQuery,
    OrQuery,
    NotQuery,
    ByMetadataQuery,
    ByTagQuery,
    ByContentQuery,
)


@pytest.fixture
def setup_manager():
    """Fixture to set up a SnapshotManager instance."""
    return SnapshotManager(max_snapshots=5)


def test_save_and_retrieve_snapshot(setup_manager):
    """Test saving and retrieving a snapshot."""
    manager = setup_manager  # Fixture provides a SnapshotManager instance

    # Define a PyTree to store
    pytree = {"a": jnp.array([1, 2, 3]), "b": {"x": jnp.array([4, 5])}}

    # Save the PyTree as a snapshot
    snapshot_id = manager.save_snapshot(pytree)

    # Retrieve the snapshot
    retrieved = manager.get_snapshot(snapshot_id)

    # Assertions to verify the integrity of the saved and retrieved PyTree
    assert jnp.array_equal(retrieved["a"], pytree["a"]), "Array 'a' does not match."
    assert jnp.array_equal(
        retrieved["b"]["x"], pytree["b"]["x"]
    ), "Array 'b.x' does not match."


def test_snapshot_metadata(setup_manager):
    """Test adding and retrieving metadata for a snapshot."""
    manager = setup_manager
    pytree = {"a": jnp.array([1, 2, 3])}
    metadata = {"experiment": "test", "iteration": 42}
    snapshot_id = manager.save_snapshot(pytree, metadata=metadata)

    retrieved_metadata = manager.get_metadata(snapshot_id)
    assert retrieved_metadata == metadata

    new_metadata = {"accuracy": 0.95}
    manager.update_metadata(snapshot_id, new_metadata)
    updated_metadata = manager.get_metadata(snapshot_id)
    assert updated_metadata["accuracy"] == 0.95
    assert updated_metadata["experiment"] == "test"


def test_snapshot_tags(setup_manager):
    """Test adding and removing tags for a snapshot."""
    manager = setup_manager
    pytree = {"a": jnp.array([1, 2, 3])}

    # Save the PyTree with initial tags
    snapshot_id = manager.save_snapshot(pytree, tags=["important"])

    # Add new tags
    manager.add_tags(snapshot_id, ["new", "experiment"])
    tags = manager.get_tags(snapshot_id)
    assert "new" in tags, "Tag 'new' should be present."
    assert "important" in tags, "Tag 'important' should be present."

    # Remove a tag
    manager.remove_tags(snapshot_id, ["important"])
    tags = manager.get_tags(snapshot_id)
    assert "important" not in tags, "Tag 'important' should not be present."
    assert "experiment" in tags, "Tag 'experiment' should still be present."


def test_snapshot_order_limit(setup_manager):
    """Test enforcing the max_snapshots limit."""
    manager = setup_manager  # Fixture provides a SnapshotManager instance

    # Save more snapshots than the max_snapshots limit
    for i in range(6):
        manager.save_snapshot({"val": i})

    # Verify the number of snapshots does not exceed the max_snapshots limit
    assert (
        len(manager.storage.snapshots) == manager.storage.max_snapshots
    ), "The number of snapshots exceeds the max_snapshots limit."

    # Verify the order of snapshots
    snapshot_order = manager.storage.snapshot_order
    assert (
        len(snapshot_order) == manager.storage.max_snapshots
    ), "The snapshot order does not match the max_snapshots limit."

    # The oldest snapshot (first inserted) should have been removed
    oldest_remaining_snapshot = snapshot_order[0]
    oldest_remaining_pytree = manager.get_snapshot(oldest_remaining_snapshot)
    assert (
        oldest_remaining_pytree["val"] == 1
    ), "The oldest snapshot was not removed correctly."


def test_save_and_load_state(tmp_path, setup_manager):
    """Test saving and loading the manager state."""
    manager = setup_manager  # Fixture provides a SnapshotManager instance

    # Create and save snapshots
    pytree1 = {"a": jnp.array([1, 2, 3])}
    pytree2 = {"b": jnp.array([4, 5, 6])}
    snapshot_id1 = manager.save_snapshot(pytree1, metadata={"key": "value1"})
    snapshot_id2 = manager.save_snapshot(pytree2, metadata={"key": "value2"})

    # Save the manager state to a file
    state_file = tmp_path / "state.pkl"
    manager.save_state(state_file)

    # Load the state into a new manager
    loaded_manager = SnapshotManager.load_state(state_file)

    # Validate that the snapshots were correctly restored
    assert len(loaded_manager.storage.snapshots) == len(
        manager.storage.snapshots
    ), "The number of snapshots in the loaded manager does not match the original."

    # Validate metadata of the restored snapshots
    assert (
        loaded_manager.get_metadata(snapshot_id1)["key"] == "value1"
    ), "Metadata for the first snapshot does not match."
    assert (
        loaded_manager.get_metadata(snapshot_id2)["key"] == "value2"
    ), "Metadata for the second snapshot does not match."

    # Validate the contents of the restored snapshots
    assert jnp.array_equal(
        loaded_manager.get_snapshot(snapshot_id1)["a"], pytree1["a"]
    ), "The first snapshot's PyTree content does not match."
    assert jnp.array_equal(
        loaded_manager.get_snapshot(snapshot_id2)["b"], pytree2["b"]
    ), "The second snapshot's PyTree content does not match."


def test_logical_queries(setup_manager):
    """Test logical queries using AndQuery, OrQuery, and NotQuery."""
    manager = setup_manager

    # Save snapshots
    manager.save_snapshot(
        {"a": 1},
        snapshot_id="snap1",
        metadata={"project": "example1"},
        tags=["experiment"],
    )
    manager.save_snapshot(
        {"b": 2},
        snapshot_id="snap2",
        metadata={"project": "example2"},
        tags=["control"],
    )
    manager.save_snapshot(
        {"c": 3},
        snapshot_id="snap3",
        metadata={"project": "example1"},
        tags=["experiment", "published"],
    )

    # Logical Query: Find snapshots in project "example1" AND tagged with "experiment"
    query = AndQuery(ByMetadataQuery("project", "example1"), ByTagQuery("experiment"))
    results = manager.query.evaluate(query)
    assert "snap1" in results and "snap3" in results, "Logical AND query failed."

    # Logical Query: Find snapshots in project "example1" OR tagged with "control"
    query = OrQuery(ByMetadataQuery("project", "example1"), ByTagQuery("control"))
    results = manager.query.evaluate(query)
    assert (
        "snap1" in results and "snap2" in results and "snap3" in results
    ), "Logical OR query failed."

    # Logical Query: Find snapshots NOT tagged with "control"
    query = NotQuery(ByTagQuery("control"))
    results = manager.query.evaluate(query)
    assert (
        "snap1" in results and "snap3" in results and "snap2" not in results
    ), "Logical NOT query failed."


from snapshot_manager.query import ByContentQuery


def test_by_content_query(setup_manager):
    """Test querying snapshots based on their content."""
    manager = setup_manager

    # Save snapshots with complex content
    manager.save_snapshot({"key": 1, "nested": {"a": 2}}, snapshot_id="snap1")
    manager.save_snapshot({"key": 3}, snapshot_id="snap2")
    manager.save_snapshot({"nested": {"b": 4}}, snapshot_id="snap3")

    # Query for snapshots containing a specific key
    query = ByContentQuery(lambda content: "key" in content)
    results = manager.query.evaluate(query)
    assert (
        "snap1" in results and "snap2" in results and "snap3" not in results
    ), "ByContentQuery failed for key existence."

    # Query for snapshots with nested key "a"
    query = ByContentQuery(
        lambda content: "nested" in content and "a" in content["nested"]
    )
    results = manager.query.evaluate(query)
    assert (
        "snap1" in results and "snap2" not in results and "snap3" not in results
    ), "ByContentQuery failed for nested key."


def test_remove_snapshot(setup_manager):
    """Test removing a snapshot."""
    manager = setup_manager

    # Save snapshots
    snapshot_id1 = manager.save_snapshot({"a": 1})
    snapshot_id2 = manager.save_snapshot({"b": 2})

    # Remove the first snapshot
    manager.remove_snapshot(snapshot_id1)

    # Verify the snapshot is removed
    with pytest.raises(KeyError, match="Snapshot with ID .* not found"):
        manager.get_snapshot(snapshot_id1)

    # Verify the remaining snapshot is unaffected
    retrieved = manager.get_snapshot(snapshot_id2)
    assert retrieved["b"] == 2, "Remaining snapshot was affected by removal."


def test_duplicate_snapshots(setup_manager):
    """Test saving duplicate snapshots."""
    manager = setup_manager

    # Save identical snapshots
    snapshot_id1 = manager.save_snapshot({"a": 1})
    snapshot_id2 = manager.save_snapshot({"a": 1})

    # Verify that the snapshots have distinct IDs
    assert snapshot_id1 != snapshot_id2, "Duplicate snapshots have the same ID."

    # Verify that both snapshots are accessible
    retrieved1 = manager.get_snapshot(snapshot_id1)
    retrieved2 = manager.get_snapshot(snapshot_id2)
    assert (
        retrieved1 == retrieved2
    ), "Duplicate snapshots should have identical content."


def test_snapshot_order_after_state_restore(tmp_path, setup_manager):
    """Test that snapshot order is preserved after restoring state."""
    manager = setup_manager

    # Save snapshots
    manager.save_snapshot({"a": 1}, snapshot_id="snap1")
    manager.save_snapshot({"b": 2}, snapshot_id="snap2")

    # Save the manager state
    state_file = tmp_path / "state.pkl"
    manager.save_state(state_file)

    # Restore the state
    restored_manager = SnapshotManager.load_state(state_file)

    # Verify that the snapshot order is preserved
    assert (
        restored_manager.storage.snapshot_order == manager.storage.snapshot_order
    ), "Snapshot order was not preserved after restoring state."


from snapshot_manager.pytree_snapshot_manager import PyTreeSnapshotManager
import jax.numpy as jnp


def test_query_by_leaf_value_simple_condition():
    """Test querying snapshots with a simple condition on leaf values."""
    manager = PyTreeSnapshotManager()

    # Save PyTree snapshots
    manager.save_snapshot(
        {"a": jnp.array([1, 2, 3]), "b": {"x": jnp.array([4, 5])}}, snapshot_id="snap1"
    )
    manager.save_snapshot(
        {"x": jnp.array([6, 7, 8]), "y": {"z": jnp.array([9])}}, snapshot_id="snap2"
    )
    manager.save_snapshot({"p": jnp.array([-1, -2])}, snapshot_id="snap3")

    # Query for snapshots where any leaf contains a value > 5
    query = manager.query.by_leaf_value(lambda x: jnp.any(x > 5))
    results = manager.query.evaluate(query)

    # Assert that only the relevant snapshots are returned
    assert "snap2" in results, "Snapshot with leaf value > 5 is missing."
    assert (
        "snap1" not in results
    ), "Snapshot with no leaf value > 5 is incorrectly included."
    assert (
        "snap3" not in results
    ), "Snapshot with no leaf value > 5 is incorrectly included."


def test_query_by_leaf_value_complex_condition():
    """Test querying snapshots with a complex condition on leaf values."""
    manager = PyTreeSnapshotManager()

    # Save PyTree snapshots
    manager.save_snapshot(
        {"a": jnp.array([1, 2, 3]), "b": {"x": jnp.array([4, 5])}}, snapshot_id="snap1"
    )
    manager.save_snapshot(
        {"x": jnp.array([-6, 7, 8]), "y": {"z": jnp.array([9])}}, snapshot_id="snap2"
    )
    manager.save_snapshot({"p": jnp.array([-1, -2])}, snapshot_id="snap3")

    # Query for snapshots where any leaf contains a negative value
    query = manager.query.by_leaf_value(lambda x: jnp.any(x < 0))
    results = manager.query.evaluate(query)

    # Assert that the relevant snapshots are returned
    assert "snap3" in results, "Snapshot with negative leaf values is missing."
    assert "snap2" in results, "Snapshot with negative leaf values is missing."
    assert (
        "snap1" not in results
    ), "Snapshot with no negative leaf values is incorrectly included."


def test_prune_snapshots_by_accuracy():
    """Test pruning snapshots by accuracy when max_snapshots is reached."""

    def cmp_by_accuracy(snapshot1, snapshot2):
        return snapshot1.metadata.get("accuracy", 0) - snapshot2.metadata.get(
            "accuracy", 0
        )

    # Initialize manager with a maximum of 3 snapshots
    manager = SnapshotManager(max_snapshots=3, cmp_function=cmp_by_accuracy)

    # Save snapshots with varying accuracy
    manager.save_snapshot({"a": 1}, snapshot_id="snap1", metadata={"accuracy": 0.5})
    manager.save_snapshot({"b": 2}, snapshot_id="snap2", metadata={"accuracy": 0.7})
    manager.save_snapshot({"c": 3}, snapshot_id="snap3", metadata={"accuracy": 0.6})

    # Save a new snapshot with higher accuracy
    manager.save_snapshot({"d": 4}, snapshot_id="snap4", metadata={"accuracy": 0.8})

    # Verify that only the top 3 snapshots are retained
    snapshots = manager.get_ranked_snapshots()
    assert (
        len(snapshots) == 3
    ), "Number of retained snapshots does not match max_snapshots."
    assert "snap1" not in snapshots, "Lowest accuracy snapshot was not removed."
    assert snapshots == [
        "snap4",
        "snap2",
        "snap3",
    ], "Snapshots are not ordered by accuracy."


def test_reject_low_ranked_snapshot():
    """Test rejecting a low-ranked snapshot when max_snapshots is reached."""

    def cmp_by_accuracy(snapshot1, snapshot2):
        return snapshot1.metadata.get("accuracy", 0) - snapshot2.metadata.get(
            "accuracy", 0
        )

    # Initialize manager with a maximum of 3 snapshots
    manager = SnapshotManager(max_snapshots=3, cmp_function=cmp_by_accuracy)

    # Save snapshots with varying accuracy
    manager.save_snapshot({"a": 1}, snapshot_id="snap1", metadata={"accuracy": 0.5})
    manager.save_snapshot({"b": 2}, snapshot_id="snap2", metadata={"accuracy": 0.7})
    manager.save_snapshot({"c": 3}, snapshot_id="snap3", metadata={"accuracy": 0.6})

    # Attempt to save a new snapshot with lower accuracy than the current lowest
    manager.save_snapshot({"e": 5}, snapshot_id="snap5", metadata={"accuracy": 0.4})

    # Verify that the low-ranked snapshot was not added
    snapshots = manager.get_ranked_snapshots()
    assert len(snapshots) == 3, "Number of snapshots exceeds max_snapshots."
    assert "snap5" not in snapshots, "Low-ranked snapshot was incorrectly added."
    assert snapshots == [
        "snap2",
        "snap3",
        "snap1",
    ], "Snapshots are not ordered correctly after rejection."


def test_override_deepcopy_on_retrieve():
    """Test overriding deepcopy_on_retrieve during a retrieval operation."""
    manager = SnapshotManager(deepcopy_on_save=False)

    # Save a snapshot
    pytree = {"a": [1, 2, 3]}
    snapshot_id = manager.save_snapshot(pytree)

    # Retrieve the snapshot without deepcopy
    retrieved = manager.get_snapshot(snapshot_id, deepcopy=False)

    # Modify the retrieved PyTree
    retrieved["a"].append(4)

    # Retrieve the snapshot again
    original = manager.get_snapshot(snapshot_id)

    # Assert the original and retrieved are not isolated
    assert original["a"] == [
        1,
        2,
        3,
        4,
    ], "Deepcopy override on retrieve did not work correctly."
    assert retrieved["a"] == [
        1,
        2,
        3,
        4,
    ], "Modified retrieved PyTree was not as expected."


def test_default_deepcopy_logic():
    """Test the default deepcopy settings for saving and retrieving snapshots."""
    manager = SnapshotManager(deepcopy_on_save=True, deepcopy_on_retrieve=True)

    # Save a snapshot with default deepcopy setting
    pytree = {"a": [1, 2, 3]}
    snapshot_id = manager.save_snapshot(pytree)

    # Modify the original PyTree
    pytree["a"].append(4)

    # Retrieve the snapshot
    retrieved = manager.get_snapshot(snapshot_id)

    # Assert the original and retrieved are isolated
    assert retrieved["a"] == [
        1,
        2,
        3,
    ], "Deepcopy on save failed to isolate the snapshot."
    assert pytree["a"] == [1, 2, 3, 4], "Original PyTree was unexpectedly modified."


def test_override_deepcopy_on_save():
    """Test overriding deepcopy_on_save during a save operation."""
    manager = SnapshotManager(deepcopy_on_save=True)

    # Save a snapshot with deepcopy explicitly disabled
    pytree = {"a": [1, 2, 3]}
    snapshot_id = manager.save_snapshot(pytree, deepcopy=False)

    # Modify the original PyTree
    pytree["a"].append(4)

    # Retrieve the snapshot
    retrieved = manager.get_snapshot(snapshot_id)

    # Assert the original and retrieved are not isolated
    assert retrieved["a"] == [
        1,
        2,
        3,
        4,
    ], "Deepcopy override on save did not work correctly."


def test_update_all_leaf_nodes(setup_manager):
    """Test updating all snapshots' leaf nodes in place."""
    manager = PyTreeSnapshotManager()

    # Save snapshots
    manager.save_snapshot({"a": 1, "b": {"x": 2}}, snapshot_id="snap1")
    manager.save_snapshot({"c": 3, "d": {"y": 4}}, snapshot_id="snap2")

    # Apply an in-place transformation to all snapshots
    manager.update_all_leaf_nodes(lambda x: x + 10)

    # Verify transformations
    snapshot1 = manager.get_snapshot("snap1", deepcopy=False)
    snapshot2 = manager.get_snapshot("snap2", deepcopy=False)
    assert (
        snapshot1["a"] == 11 and snapshot1["b"]["x"] == 12
    ), "Snapshot1 not updated correctly."
    assert (
        snapshot2["c"] == 13 and snapshot2["d"]["y"] == 14
    ), "Snapshot2 not updated correctly."


def test_inplace_leaf_transformation(setup_manager):
    """Test in-place leaf transformation for specific snapshots."""
    manager = PyTreeSnapshotManager()

    # Save snapshots
    snapshot_id1 = manager.save_snapshot({"a": 1, "b": {"x": 2}})
    snapshot_id2 = manager.save_snapshot({"c": 3, "d": {"y": 4}})

    # Apply an in-place transformation to double each leaf value
    manager.update_leaf_nodes([snapshot_id1, snapshot_id2], lambda x: x * 2)

    # Retrieve the snapshots and verify transformation
    snapshot1 = manager.get_snapshot(snapshot_id1, deepcopy=False)
    snapshot2 = manager.get_snapshot(snapshot_id2, deepcopy=False)
    assert (
        snapshot1["a"] == 2 and snapshot1["b"]["x"] == 4
    ), "Snapshot1 not transformed correctly."
    assert (
        snapshot2["c"] == 6 and snapshot2["d"]["y"] == 8
    ), "Snapshot2 not transformed correctly."


def test_combine_snapshots_average(setup_manager):
    """Test combining snapshots using an average function."""
    manager = PyTreeSnapshotManager()

    # Save snapshots with PyTree structures
    snapshot1 = {"layer1": jnp.array([1.0, 2.0]), "layer2": jnp.array([3.0])}
    snapshot2 = {"layer1": jnp.array([4.0, 5.0]), "layer2": jnp.array([6.0])}
    snapshot3 = {"layer1": jnp.array([7.0, 8.0]), "layer2": jnp.array([9.0])}

    manager.save_snapshot(snapshot1, snapshot_id="snap1")
    manager.save_snapshot(snapshot2, snapshot_id="snap2")
    manager.save_snapshot(snapshot3, snapshot_id="snap3")

    # Combine snapshots with an average function
    def average_leaves(leaves):
        return sum(leaves) / len(leaves)

    combined_pytree = manager.combine_snapshots(
        snapshot_ids=["snap1", "snap2", "snap3"], combine_fn=average_leaves
    )

    # Verify the combined PyTree
    # Expected result
    expected_pytree = {"layer1": jnp.array([4.0, 5.0]), "layer2": jnp.array([6.0])}

    # Verify the combined PyTree
    for key in combined_pytree.keys():
        assert jnp.array_equal(
            combined_pytree[key], expected_pytree[key]
        ), f"Mismatch for key {key}: {combined_pytree[key]} != {expected_pytree[key]}"