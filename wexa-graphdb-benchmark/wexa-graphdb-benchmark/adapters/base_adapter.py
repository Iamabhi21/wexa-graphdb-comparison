"""
Every platform adapter implements this interface so harness/workloads.py can
drive all five platforms identically. Keep each adapter's actual query text
visible and commented -- the README methodology depends on being able to show
"here is the literal query run on each platform."
"""
from abc import ABC, abstractmethod


class GraphAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def connect(self):
        """Open a connection/driver. Raise clearly if credentials are missing."""

    @abstractmethod
    def close(self):
        """Close the connection cleanly."""

    @abstractmethod
    def clear(self):
        """Wipe all data so repeated runs start from empty."""

    @abstractmethod
    def create_indexes(self):
        """Create whatever index(es) this platform uses for the indexed-lookup
        workload. Record what was indexed -- the README must state this."""

    @abstractmethod
    def load_data(self, nodes: list, edges: list, batch_size: int = 1000) -> dict:
        """
        Bulk-load nodes and edges in batches of `batch_size`.
        Returns {"nodes_per_sec": float, "edges_per_sec": float, "wall_clock_s": float}.
        """

    @abstractmethod
    def traverse(self, start_id: str, hops: int) -> list:
        """Run an N-hop traversal from start_id. Return the result (used only
        to confirm correctness) -- callers measure the wall-clock separately."""

    @abstractmethod
    def point_lookup(self, node_id: str):
        """Fetch a single node by its indexed primary id."""

    @abstractmethod
    def indexed_lookup(self, value):
        """Fetch nodes by a secondary indexed/filtered property."""

    @abstractmethod
    def aggregate(self):
        """Run a count / group-by style aggregation over a label or rel type."""

    @abstractmethod
    def write_edge(self, src: str, dst: str):
        """Single-edge write, used by the mixed read/write workload."""

    def footprint(self) -> dict:
        """Optional: stored data size / memory usage, if the platform exposes it.
        Return {"stored_bytes": ..., "notes": "..."} or {"notes": "not observable"}."""
        return {"notes": "not observable"}
