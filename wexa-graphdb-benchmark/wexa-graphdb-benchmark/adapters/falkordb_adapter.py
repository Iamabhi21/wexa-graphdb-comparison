"""
FalkorDB Cloud adapter. FalkorDB speaks Cypher-like queries over the Redis
protocol (GRAPH.QUERY) rather than Bolt -- architecturally the most different
platform in the comparison, which is exactly why it's included (see README
"why chosen"). Query text is intentionally near-identical to cypher_adapter.py
so any latency delta is attributable to the engine, not to different queries.
"""
import os
import time
from falkordb import FalkorDB
from adapters.base_adapter import GraphAdapter


class FalkorDBAdapter(GraphAdapter):
    name = "falkordb"

    def __init__(self, host: str, port: int, password: str, graph_name: str = "benchmark"):
        self.host = host
        self.port = port
        self.password = password
        self.graph_name = graph_name
        self.db = None
        self.graph = None

    @classmethod
    def from_env(cls):
        host = os.environ.get("FALKORDB_HOST")
        port = int(os.environ.get("FALKORDB_PORT", "6379"))
        password = os.environ.get("FALKORDB_PASSWORD")
        if not host:
            raise RuntimeError("Missing FALKORDB_HOST / FALKORDB_PORT / FALKORDB_PASSWORD in .env")
        return cls(host, port, password)

    def connect(self):
        self.db = FalkorDB(host=self.host, port=self.port, password=self.password)
        self.graph = self.db.select_graph(self.graph_name)

    def close(self):
        pass  # falkordb client has no explicit close

    def clear(self):
        try:
            self.graph.delete()
        except Exception:
            pass  # graph may not exist yet on first run

    def create_indexes(self):
        self.graph.query("CREATE INDEX FOR (n:Node) ON (n.id)")
        self.graph.query("CREATE INDEX FOR (n:Node) ON (n.group)")

    def load_data(self, nodes: list, edges: list, batch_size: int = 1000) -> dict:
        start = time.perf_counter()
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            rows = ", ".join(f"{{id: '{n}', group: {int(n) % 10 if n.isdigit() else 0}}}" for n in batch)
            self.graph.query(f"UNWIND [{rows}] AS row CREATE (:Node {{id: row.id, group: row.group}})")
        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            rows = ", ".join(f"{{src: '{s}', dst: '{d}'}}" for s, d in batch)
            self.graph.query(
                f"UNWIND [{rows}] AS row "
                "MATCH (a:Node {id: row.src}), (b:Node {id: row.dst}) "
                "CREATE (a)-[:CONNECTS]->(b)"
            )
        elapsed = time.perf_counter() - start
        return {
            "nodes_per_sec": len(nodes) / elapsed if elapsed > 0 else None,
            "edges_per_sec": len(edges) / elapsed if elapsed > 0 else None,
            "wall_clock_s": round(elapsed, 3),
        }

    def traverse(self, start_id: str, hops: int) -> list:
        q = f"MATCH (a:Node {{id: '{start_id}'}})-[:CONNECTS*1..{hops}]->(b:Node) RETURN DISTINCT b.id"
        result = self.graph.query(q)
        return [row[0] for row in result.result_set]

    def point_lookup(self, node_id: str):
        result = self.graph.query(f"MATCH (n:Node {{id: '{node_id}'}}) RETURN n")
        return result.result_set

    def indexed_lookup(self, value):
        result = self.graph.query(f"MATCH (n:Node {{group: {value}}}) RETURN n LIMIT 100")
        return result.result_set

    def aggregate(self):
        result = self.graph.query("MATCH (n:Node) RETURN n.group, count(*) ORDER BY n.group")
        return result.result_set

    def write_edge(self, src: str, dst: str):
        self.graph.query(
            f"MERGE (a:Node {{id: '{src}'}}) MERGE (b:Node {{id: '{dst}'}}) MERGE (a)-[:CONNECTS]->(b)"
        )

    def footprint(self) -> dict:
        try:
            info = self.graph.query("CALL dbms.info()")
            return {"notes": str(info.result_set)}
        except Exception as e:
            return {"notes": f"not observable ({type(e).__name__})"}
