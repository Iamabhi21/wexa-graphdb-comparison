"""
ArangoDB Oasis adapter. ArangoDB is multi-model and queried with AQL, not
Cypher -- the query text below is the hand-translated AQL equivalent of the
Cypher queries in cypher_adapter.py / falkordb_adapter.py. Document this
language difference explicitly in the README/caveats; it's the assignment's
own instruction (§5.3).
"""
import os
import time
from arango import ArangoClient
from adapters.base_adapter import GraphAdapter


class ArangoAdapter(GraphAdapter):
    name = "arangodb"

    def __init__(self, url: str, user: str, password: str, db_name: str):
        self.url = url
        self.user = user
        self.password = password
        self.db_name = db_name
        self.client = None
        self.db = None
        self.graph = None

    @classmethod
    def from_env(cls):
        url = os.environ.get("ARANGO_URL")
        user = os.environ.get("ARANGO_USER", "root")
        password = os.environ.get("ARANGO_PASSWORD")
        db_name = os.environ.get("ARANGO_DB", "benchmark")
        if not all([url, password]):
            raise RuntimeError("Missing ARANGO_URL / ARANGO_PASSWORD in .env")
        return cls(url, user, password, db_name)

    def connect(self):
        self.client = ArangoClient(hosts=self.url)
        sys_db = self.client.db("_system", username=self.user, password=self.password)
        if not sys_db.has_database(self.db_name):
            sys_db.create_database(self.db_name)
        self.db = self.client.db(self.db_name, username=self.user, password=self.password)

        if not self.db.has_collection("nodes"):
            self.db.create_collection("nodes")
        if not self.db.has_collection("edges"):
            self.db.create_collection("edges", edge=True)
        if not self.db.has_graph("benchmark_graph"):
            self.graph = self.db.create_graph(
                "benchmark_graph",
                edge_definitions=[{
                    "edge_collection": "edges",
                    "from_vertex_collections": ["nodes"],
                    "to_vertex_collections": ["nodes"],
                }],
            )
        else:
            self.graph = self.db.graph("benchmark_graph")

    def close(self):
        pass  # python-arango has no persistent connection to close explicitly

    def clear(self):
        self.db.collection("nodes").truncate()
        self.db.collection("edges").truncate()

    def create_indexes(self):
        self.db.collection("nodes").add_persistent_index(fields=["orig_id"], unique=True)
        self.db.collection("nodes").add_persistent_index(fields=["group"])

    def load_data(self, nodes: list, edges: list, batch_size: int = 1000) -> dict:
        start = time.perf_counter()
        nodes_coll = self.db.collection("nodes")
        edges_coll = self.db.collection("edges")

        # ArangoDB needs its own document keys; keep a mapping from the
        # dataset's original id to Arango's "_key" for edge creation.
        key_map = {}
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            docs = [{"_key": f"n{n}", "orig_id": n, "group": int(n) % 10 if n.isdigit() else 0} for n in batch]
            nodes_coll.insert_many(docs, overwrite=True)
            for n in batch:
                key_map[n] = f"n{n}"

        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            docs = [{"_from": f"nodes/{key_map.get(s, 'n'+s)}",
                     "_to": f"nodes/{key_map.get(d, 'n'+d)}"} for s, d in batch]
            edges_coll.insert_many(docs, overwrite=True)

        elapsed = time.perf_counter() - start
        return {
            "nodes_per_sec": len(nodes) / elapsed if elapsed > 0 else None,
            "edges_per_sec": len(edges) / elapsed if elapsed > 0 else None,
            "wall_clock_s": round(elapsed, 3),
        }

    def traverse(self, start_id: str, hops: int) -> list:
        aql = """
            FOR v IN 1..@hops OUTBOUND @start GRAPH 'benchmark_graph'
            RETURN DISTINCT v.orig_id
        """
        cursor = self.db.aql.execute(aql, bind_vars={"hops": hops, "start": f"nodes/n{start_id}"})
        return list(cursor)

    def point_lookup(self, node_id: str):
        return self.db.collection("nodes").get(f"n{node_id}")

    def indexed_lookup(self, value):
        aql = "FOR n IN nodes FILTER n.group == @g LIMIT 100 RETURN n"
        return list(self.db.aql.execute(aql, bind_vars={"g": value}))

    def aggregate(self):
        aql = """
            FOR n IN nodes
            COLLECT grp = n.group WITH COUNT INTO cnt
            SORT grp
            RETURN {grp, cnt}
        """
        return list(self.db.aql.execute(aql))

    def write_edge(self, src: str, dst: str):
        self.db.collection("edges").insert({"_from": f"nodes/n{src}", "_to": f"nodes/n{dst}"}, overwrite=True)

    def footprint(self) -> dict:
        try:
            stats = self.db.collection("nodes").statistics()
            return {"stored_bytes": stats.get("figures", {}).get("documentsSize"), "notes": "nodes collection only"}
        except Exception as e:
            return {"notes": f"not observable ({type(e).__name__})"}
