"""
Shared adapter for every platform that speaks the Neo4j Bolt protocol +
Cypher: CognoDB Cloud, Neo4j AuraDB, and Memgraph Cloud. Using one adapter
class for all three is itself part of the fairness story -- identical driver,
identical query text, identical batching logic for all three platforms.
"""
import os
import time
from neo4j import GraphDatabase
from adapters.base_adapter import GraphAdapter


class CypherAdapter(GraphAdapter):
    def __init__(self, name: str, uri: str, user: str, password: str):
        self.name = name
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None

    @classmethod
    def from_env(cls, name: str, uri_var: str, user_var: str, pass_var: str):
        uri = os.environ.get(uri_var)
        user = os.environ.get(user_var)
        password = os.environ.get(pass_var)
        if not all([uri, user, password]):
            raise RuntimeError(
                f"Missing env vars for {name}: expected {uri_var}, {user_var}, {pass_var} in .env"
            )
        return cls(name, uri, user, password)

    def connect(self):
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self.driver.verify_connectivity()

    def close(self):
        if self.driver:
            self.driver.close()

    def clear(self):
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")

    def create_indexes(self):
        # Indexed on Node.id (primary key) and Node.group (secondary/filtered
        # property used by the indexed-lookup and aggregation workloads).
        with self.driver.session() as s:
            s.run("CREATE INDEX node_id_idx IF NOT EXISTS FOR (n:Node) ON (n.id)")
            s.run("CREATE INDEX node_group_idx IF NOT EXISTS FOR (n:Node) ON (n.group)")

    def load_data(self, nodes: list, edges: list, batch_size: int = 1000) -> dict:
        start = time.perf_counter()
        with self.driver.session() as s:
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i:i + batch_size]
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (n:Node {id: row.id})
                    SET n.group = toInteger(row.id) % 10
                    """,
                    rows=[{"id": n} for n in batch],
                )
            for i in range(0, len(edges), batch_size):
                batch = edges[i:i + batch_size]
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (a:Node {id: row.src}), (b:Node {id: row.dst})
                    MERGE (a)-[:CONNECTS]->(b)
                    """,
                    rows=[{"src": s_, "dst": d_} for s_, d_ in batch],
                )
        elapsed = time.perf_counter() - start
        return {
            "nodes_per_sec": len(nodes) / elapsed if elapsed > 0 else None,
            "edges_per_sec": len(edges) / elapsed if elapsed > 0 else None,
            "wall_clock_s": round(elapsed, 3),
        }

    def traverse(self, start_id: str, hops: int) -> list:
        query = f"""
            MATCH (a:Node {{id: $start}})-[:CONNECTS*1..{hops}]->(b:Node)
            RETURN DISTINCT b.id AS id
        """
        with self.driver.session() as s:
            return [r["id"] for r in s.run(query, start=start_id)]

    def point_lookup(self, node_id: str):
        with self.driver.session() as s:
            return s.run("MATCH (n:Node {id: $id}) RETURN n", id=node_id).single()

    def indexed_lookup(self, value):
        with self.driver.session() as s:
            return list(s.run("MATCH (n:Node {group: $g}) RETURN n LIMIT 100", g=value))

    def aggregate(self):
        with self.driver.session() as s:
            return list(s.run(
                "MATCH (n:Node) RETURN n.group AS grp, count(*) AS cnt ORDER BY grp"
            ))

    def write_edge(self, src: str, dst: str):
        with self.driver.session() as s:
            s.run(
                """
                MERGE (a:Node {id: $src})
                MERGE (b:Node {id: $dst})
                MERGE (a)-[:CONNECTS]->(b)
                """,
                src=src, dst=dst,
            )

    def footprint(self) -> dict:
        # Works on Neo4j/Memgraph; CognoDB may not expose APOC / dbms procs on
        # the free tier -- catch and report "not observable" rather than fail.
        try:
            with self.driver.session() as s:
                rec = s.run(
                    "CALL apoc.meta.stats() YIELD nodeCount, relCount RETURN nodeCount, relCount"
                ).single()
                return {"node_count": rec["nodeCount"], "rel_count": rec["relCount"]}
        except Exception as e:
            return {"notes": f"not observable ({type(e).__name__})"}


def cognodb_adapter():
    return CypherAdapter.from_env("cognodb", "COGNODB_URI", "COGNODB_USER", "COGNODB_PASSWORD")


def neo4j_adapter():
    return CypherAdapter.from_env("neo4j-aura", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")


def memgraph_adapter():
    return CypherAdapter.from_env("memgraph", "MEMGRAPH_URI", "MEMGRAPH_USER", "MEMGRAPH_PASSWORD")
