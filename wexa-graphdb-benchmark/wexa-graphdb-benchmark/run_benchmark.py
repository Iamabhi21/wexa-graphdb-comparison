"""
Main entrypoint. Loads the dataset, runs the requested workloads against the
requested platform(s), and writes results/<platform>.json.

Examples:
    python run_benchmark.py --platform all --step all
    python run_benchmark.py --platform cognodb --step load
    python run_benchmark.py --platform neo4j --step query --concurrency 1 10 40
"""
import argparse
import csv
import json
import os
import sys
import traceback

from dotenv import load_dotenv

from harness import workloads
from adapters.cypher_adapter import cognodb_adapter, neo4j_adapter, memgraph_adapter
from adapters.falkordb_adapter import FalkorDBAdapter
from adapters.arango_adapter import ArangoAdapter

load_dotenv()

PLATFORMS = {
    "cognodb": cognodb_adapter,
    "neo4j": neo4j_adapter,
    "memgraph": memgraph_adapter,
    "falkordb": FalkorDBAdapter.from_env,
    "arangodb": ArangoAdapter.from_env,
}


def load_dataset(data_dir="data/raw"):
    nodes = []
    with open(os.path.join(data_dir, "nodes.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            nodes.append(row["id"])
    edges = []
    with open(os.path.join(data_dir, "edges.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            edges.append((row["src"], row["dst"]))
    return nodes, edges


def run_one_platform(name: str, steps: list, concurrencies: list, nodes: list, edges: list) -> dict:
    print(f"\n=== {name} ===")
    result = {"platform": name, "caveats": []}
    factory = PLATFORMS[name]
    try:
        adapter = factory()
    except Exception as e:
        print(f"  SKIPPED: could not construct adapter ({e})")
        result["caveats"].append(f"adapter construction failed: {e}")
        return result

    try:
        adapter.connect()
    except Exception as e:
        print(f"  SKIPPED: could not connect ({e})")
        result["caveats"].append(f"connection failed: {e}")
        return result

    try:
        if "load" in steps or "all" in steps:
            print("  loading data...")
            result["load"] = workloads.run_load(adapter, nodes, edges)
            print(f"  load: {result['load']}")

        if "query" in steps or "all" in steps:
            print("  running traversals...")
            result["traversals"] = workloads.run_traversals(adapter, nodes)
            print("  running lookups...")
            result["lookups"] = workloads.run_lookups(adapter, nodes)
            print("  running aggregation...")
            result["aggregation"] = workloads.run_aggregation(adapter)
            print("  running mixed workload sweep...")
            result["mixed"] = []
            for c in concurrencies:
                mixed = workloads.run_mixed(adapter, nodes, concurrency=c, duration_s=15)
                result["mixed"].append(mixed)
                if mixed["errors"] > 0:
                    result["caveats"].append(f"{mixed['errors']} errors during mixed workload at concurrency={c}")

            print("  checking footprint...")
            result["footprint"] = adapter.footprint()
    except Exception as e:
        print(f"  ERROR during workload run: {e}")
        traceback.print_exc()
        result["caveats"].append(f"workload error: {e}")
    finally:
        adapter.close()

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", nargs="+", default=["all"],
                     choices=list(PLATFORMS.keys()) + ["all"])
    ap.add_argument("--step", nargs="+", default=["all"], choices=["load", "query", "all"])
    ap.add_argument("--concurrency", nargs="+", type=int, default=[1, 10, 40])
    ap.add_argument("--data-dir", default="data/raw")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args()

    platforms = list(PLATFORMS.keys()) if "all" in args.platform else args.platform

    nodes, edges = load_dataset(args.data_dir)
    print(f"Loaded dataset: {len(nodes)} nodes, {len(edges)} edges")

    os.makedirs(args.results_dir, exist_ok=True)
    for name in platforms:
        result = run_one_platform(name, args.step, args.concurrency, nodes, edges)
        out_path = os.path.join(args.results_dir, f"{name}.json")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
