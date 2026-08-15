"""
Reads results/<platform>.json for every platform and renders the required
results matrix (assignment §5.2/§6) as markdown tables into RESULTS.md.

Usage:
    python -m harness.report --input results/ --output RESULTS.md
"""
import argparse
import glob
import json
import os


def load_all_results(input_dir: str) -> dict:
    results = {}
    for path in glob.glob(os.path.join(input_dir, "*.json")):
        platform = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            results[platform] = json.load(f)
    return results


def md_row(cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render(results: dict) -> str:
    platforms = sorted(results.keys())
    lines = ["# Benchmark Results\n"]

    # Ingest
    lines.append("## Data loading\n")
    lines.append(md_row(["Platform", "Nodes/sec", "Rels/sec", "Wall clock (s)"]))
    lines.append(md_row(["---"] * 4))
    for p in platforms:
        load = results[p].get("load", {})
        lines.append(md_row([
            p,
            round(load.get("nodes_per_sec", 0) or 0, 1),
            round(load.get("edges_per_sec", 0) or 0, 1),
            load.get("wall_clock_s", "-"),
        ]))

    # Traversals
    lines.append("\n## Traversals (p50 / p95 ms)\n")
    lines.append(md_row(["Platform", "1-hop", "2-hop", "3-hop"]))
    lines.append(md_row(["---"] * 4))
    for p in platforms:
        trav = results[p].get("traversals", {})
        row = [p]
        for hop_key in ("1_hop", "2_hop", "3_hop"):
            s = trav.get(hop_key, {})
            row.append(f"{s.get('p50_ms', '-')} / {s.get('p95_ms', '-')}")
        lines.append(md_row(row))

    # Lookups
    lines.append("\n## Lookups (p50 / p95 ms)\n")
    lines.append(md_row(["Platform", "Point lookup", "Indexed lookup"]))
    lines.append(md_row(["---"] * 3))
    for p in platforms:
        lk = results[p].get("lookups", {})
        pl = lk.get("point_lookup", {})
        il = lk.get("indexed_lookup", {})
        lines.append(md_row([
            p,
            f"{pl.get('p50_ms', '-')} / {pl.get('p95_ms', '-')}",
            f"{il.get('p50_ms', '-')} / {il.get('p95_ms', '-')}",
        ]))

    # Aggregation
    lines.append("\n## Aggregation (p50 / p95 ms)\n")
    lines.append(md_row(["Platform", "Group-by count"]))
    lines.append(md_row(["---"] * 2))
    for p in platforms:
        agg = results[p].get("aggregation", {})
        lines.append(md_row([p, f"{agg.get('p50_ms', '-')} / {agg.get('p95_ms', '-')}"]))

    # Mixed workload
    lines.append("\n## Mixed read/write workload\n")
    lines.append(md_row(["Platform", "Concurrency", "R/W ratio", "QPS", "Errors"]))
    lines.append(md_row(["---"] * 5))
    for p in platforms:
        for run in results[p].get("mixed", []):
            lines.append(md_row([
                p, run.get("concurrency"), run.get("read_write_ratio"),
                run.get("qps"), run.get("errors"),
            ]))

    # Footprint
    lines.append("\n## Footprint\n")
    lines.append(md_row(["Platform", "Notes"]))
    lines.append(md_row(["---"] * 2))
    for p in platforms:
        fp = results[p].get("footprint", {})
        lines.append(md_row([p, fp]))

    # Caveats
    lines.append("\n## Caveats\n")
    for p in platforms:
        caveats = results[p].get("caveats", [])
        if caveats:
            lines.append(f"- **{p}**: " + "; ".join(caveats))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="results/")
    ap.add_argument("--output", default="RESULTS.md")
    args = ap.parse_args()

    results = load_all_results(args.input)
    if not results:
        print(f"No result JSON files found in {args.input} -- run run_benchmark.py first.")
        return
    md = render(results)
    with open(args.output, "w") as f:
        f.write(md)
    print(f"Wrote {args.output} from {len(results)} platform(s): {', '.join(sorted(results.keys()))}")


if __name__ == "__main__":
    main()
