"""
Downloads a public SNAP graph dataset and normalizes it into two CSV files
that every adapter loads from, so every platform ingests byte-identical data:

    data/raw/nodes.csv   -- one column: id
    data/raw/edges.csv   -- two columns: src,dst

Usage:
    python data/download_dataset.py --dataset email-enron
    python data/download_dataset.py --dataset soc-slashdot --max-edges 500000
"""
import argparse
import gzip
import io
import os
import sys
import urllib.request

DATASETS = {
    # name -> (url, description)
    "email-enron": (
        "https://snap.stanford.edu/data/email-Enron.txt.gz",
        "SNAP email-Enron: ~36,692 nodes / ~183,831 edges",
    ),
    "soc-slashdot": (
        "https://snap.stanford.edu/data/soc-Slashdot0811.txt.gz",
        "SNAP soc-Slashdot0811: ~77,360 nodes / ~905,468 edges (sample down with --max-edges)",
    ),
}


def download(url: str) -> bytes:
    print(f"Downloading {url} ...")
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def parse_edgelist(raw_gz: bytes, max_edges: int | None):
    edges = []
    nodes = set()
    with gzip.open(io.BytesIO(raw_gz), "rt") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            src, dst = parts[0], parts[1]
            edges.append((src, dst))
            nodes.add(src)
            nodes.add(dst)
            if max_edges and len(edges) >= max_edges:
                break
    return nodes, edges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=DATASETS.keys(), default="email-enron")
    ap.add_argument("--max-edges", type=int, default=None,
                     help="Cap the number of edges loaded (use to keep e.g. soc-slashdot in the 100k-500k range)")
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "raw"))
    args = ap.parse_args()

    url, desc = DATASETS[args.dataset]
    print(f"Dataset: {args.dataset} -- {desc}")

    raw_gz = download(url)
    nodes, edges = parse_edgelist(raw_gz, args.max_edges)

    os.makedirs(args.out_dir, exist_ok=True)
    nodes_path = os.path.join(args.out_dir, "nodes.csv")
    edges_path = os.path.join(args.out_dir, "edges.csv")

    with open(nodes_path, "w") as f:
        f.write("id\n")
        for n in sorted(nodes, key=lambda x: int(x) if x.isdigit() else x):
            f.write(f"{n}\n")

    with open(edges_path, "w") as f:
        f.write("src,dst\n")
        for src, dst in edges:
            f.write(f"{src},{dst}\n")

    print(f"Wrote {len(nodes)} nodes -> {nodes_path}")
    print(f"Wrote {len(edges)} edges -> {edges_path}")
    print("Record these exact counts in your README results section.")


if __name__ == "__main__":
    main()
