# Graph Database Cloud Benchmark — CognoDB vs. Managed Graph Platforms

A reproducible benchmark comparing **CognoDB Cloud** against four other managed
graph database platforms on identical hardware tiers, identical data, and
identical query workloads.
See `ANALYSIS.md` (generated
> after a run) for the write-up of findings.

## Platforms compared

| Platform | Free/entry tier used | Protocol | Why chosen |
|---|---|---|---|
| **CognoDB Cloud** | c0 (0.5 vCPU burstable, 256 MB RAM, 1 GB disk) | Bolt / Cypher | Subject of the benchmark |
| **Neo4j AuraDB Free** | 0.5 vCPU / 1 GB RAM / ~50k node instance cap | Bolt / Cypher | CognoDB speaks the Neo4j wire protocol — this is the most direct apples-to-apples comparison |
| **Memgraph Cloud** | Free tier (shared, small instance) | Bolt / Cypher | In-memory graph engine, same query language, different execution model |
| **FalkorDB Cloud** | Free tier | Redis protocol / Cypher-like (GRAPH.QUERY) | Sparse-matrix backed graph engine — architecturally very different from the above three |
| **ArangoDB Oasis** | Free trial, smallest instance size | HTTP / AQL | Multi-model database; different query language, useful for measuring the cost of language/driver differences |

Fill in the **actual provisioned specs** for each platform here once instances
are created (`vCPU`, `RAM`, `disk`) — the free tiers above are approximate and
should be confirmed against each provider's current console at setup time.

## Dataset

**SNAP `email-Enron`** — real communication network, ~36,692 nodes / 183,831
edges (within the 100k–500k relationship target range from the assignment).
Source: https://snap.stanford.edu/data/email-Enron.html

Swap-in alternative if you want more edges: **SNAP `soc-Slashdot0811`**
(~77k nodes / ~905k edges — sample down to ~500k edges) or a filtered slice of
`soc-Pokec`. The downloader script (`data/download_dataset.py`) handles either
and reports the exact node/edge count actually loaded.

Load method: identical for every platform — `UNWIND`-batched Cypher writes (or
the platform's equivalent) in batches of 1,000 relationships, via the
`adapters/*.py` `load_data()` implementation for each platform. No
platform-specific bulk-import tool is used, so ingest numbers reflect
driver-level batched writes, not each vendor's fastest possible bulk loader —
this is called out explicitly as a methodology caveat below.

## Setup

1. Clone this repo and create a virtualenv:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in connection details for every
   platform you provision (see "Provisioning each platform" below).
3. Download the dataset:
   ```bash
   python data/download_dataset.py --dataset email-enron
   ```
4. Run the full benchmark suite (all platforms, all workloads):
   ```bash
   python run_benchmark.py --platform all --step all
   ```
   Or run one platform / one step at a time — see `run_benchmark.py --help`.
5. Generate the results tables and charts:
   ```bash
   python -m harness.report --input results/ --output RESULTS.md
   ```

## Provisioning each platform

- **CognoDB Cloud**: sign up at console.cognodb.com, create a free `c0`
  instance, copy the `bolt+s://` URI and the one-time `cognodb` password into
  `.env` as `COGNODB_URI` / `COGNODB_PASSWORD`.
- **Neo4j AuraDB Free**: console.neo4j.io → create a free instance → copy
  `NEO4J_URI` / `NEO4J_PASSWORD` into `.env`.
- **Memgraph Cloud**: cloud.memgraph.com → create a free project → copy
  `MEMGRAPH_URI` / `MEMGRAPH_PASSWORD`.
- **FalkorDB Cloud**: app.falkordb.cloud → create a free instance → copy
  `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_PASSWORD`.
- **ArangoDB Oasis**: cloud.arangodb.com → start a free trial, smallest
  deployment size → copy `ARANGO_URL` / `ARANGO_USER` / `ARANGO_PASSWORD`.

**Never commit `.env`** — it's already in `.gitignore`. `run_benchmark.py`
reads all credentials from environment variables only.

## Methodology

- Same dataset, same logical queries, same client machine/region for every
  platform (run all platforms from the same machine in the same session).
- Warm-up: each workload runs 10 unmeasured warm-up iterations before the
  ≥100 measured iterations.
- Read latencies report p50 and p95, computed from raw per-call timings
  (`harness/metrics.py`), not just averages.
- Mixed workload: configurable concurrency (`--concurrency`, default sweep
  1/10/40) using a thread pool, 80/20 read/write mix by default.
- All caveats (throttling, timeouts, failed runs, query-language differences)
  are logged to `results/<platform>_caveats.json` and surfaced in
  `RESULTS.md` automatically — don't hand-edit them out.

## Required metrics (from assignment §5.2)

| Category | Metric | Where measured |
|---|---|---|
| Data loading | Ingest throughput | `harness/workloads.py::run_load` |
| Traversals | 1/2/3-hop p50, p95 | `harness/workloads.py::run_traversals` |
| Lookups | Point + indexed lookup p50, p95 | `harness/workloads.py::run_lookups` |
| Aggregations | Count/group-by p50, p95 | `harness/workloads.py::run_aggregation` |
| Mixed workload | Concurrent QPS | `harness/workloads.py::run_mixed` |
| Footprint | Storage/memory where observable | `adapters/*.py::footprint()` |

## Repo layout

```
adapters/          One adapter per platform, all implementing base_adapter.GraphAdapter
harness/           Platform-agnostic workload runners, metrics, report generator
data/              Dataset download + conversion to a common (nodes.csv, edges.csv) format
run_benchmark.py   CLI entrypoint
results/           Raw JSON results + generated RESULTS.md / charts (gitignored except .gitkeep)
```

## Known caveats (fill in / extend after each run)

- Free-tier instances are burstable/shared — expect variance run to run;
  report is based on N repeated runs (see `--repeats` flag), not a single pass.
- Ingest uses driver-level batched writes for every platform for a fair
  comparison, not each vendor's fastest bulk-import path — a "best-case
  ingest" number using native bulk tools would look different and is called
  out separately if measured.
- ArangoDB's AQL and FalkorDB's GRAPH.QUERY are not Cypher — equivalent-intent
  queries were hand-translated per platform; see `adapters/*.py` for the exact
  query text used on each.
