"""
Platform-agnostic workload runners. Every function takes a connected
adapter (adapters.base_adapter.GraphAdapter) and returns a plain dict that
harness/report.py can turn into markdown tables -- no platform-specific
branching lives here, which is the whole point of the adapter interface.
"""
import random
import concurrent.futures as cf
from harness.metrics import Timer

WARMUP_ITERS = 10
MEASURED_ITERS = 100


def run_load(adapter, nodes: list, edges: list) -> dict:
    adapter.clear()
    load_stats = adapter.load_data(nodes, edges)
    adapter.create_indexes()
    return load_stats


def _sample_ids(nodes: list, k: int) -> list:
    k = min(k, len(nodes))
    return random.sample(nodes, k)


def run_traversals(adapter, nodes: list, hops=(1, 2, 3),
                    warmup=WARMUP_ITERS, iters=MEASURED_ITERS) -> dict:
    results = {}
    for h in hops:
        sample_ids = _sample_ids(nodes, warmup + iters)
        for sid in sample_ids[:warmup]:
            adapter.traverse(sid, h)
        timer = Timer()
        for sid in sample_ids[warmup:warmup + iters]:
            with timer.measure():
                adapter.traverse(sid, h)
        results[f"{h}_hop"] = timer.summary()
    return results


def run_lookups(adapter, nodes: list, warmup=WARMUP_ITERS, iters=MEASURED_ITERS) -> dict:
    sample_ids = _sample_ids(nodes, warmup + iters)
    for sid in sample_ids[:warmup]:
        adapter.point_lookup(sid)
    point_timer = Timer()
    for sid in sample_ids[warmup:warmup + iters]:
        with point_timer.measure():
            adapter.point_lookup(sid)

    for _ in range(warmup):
        adapter.indexed_lookup(random.randint(0, 9))
    indexed_timer = Timer()
    for _ in range(iters):
        with indexed_timer.measure():
            adapter.indexed_lookup(random.randint(0, 9))

    return {"point_lookup": point_timer.summary(), "indexed_lookup": indexed_timer.summary()}


def run_aggregation(adapter, warmup=WARMUP_ITERS, iters=MEASURED_ITERS) -> dict:
    for _ in range(warmup):
        adapter.aggregate()
    timer = Timer()
    for _ in range(iters):
        with timer.measure():
            adapter.aggregate()
    return timer.summary()


def run_mixed(adapter, nodes: list, concurrency: int = 10, duration_s: int = 15,
              read_write_ratio: float = 0.8) -> dict:
    """
    Sustained mixed read/write throughput at a given client concurrency.
    read_write_ratio=0.8 means 80% point-lookups, 20% single-edge writes.
    """
    import time
    stop_at = time.perf_counter() + duration_s
    counters = {"reads": 0, "writes": 0, "errors": 0}

    def worker():
        local_reads = local_writes = local_errors = 0
        while time.perf_counter() < stop_at:
            try:
                if random.random() < read_write_ratio:
                    adapter.point_lookup(random.choice(nodes))
                    local_reads += 1
                else:
                    a, b = random.sample(nodes, 2)
                    adapter.write_edge(a, b)
                    local_writes += 1
            except Exception:
                local_errors += 1
        return local_reads, local_writes, local_errors

    start = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(worker) for _ in range(concurrency)]
        for fut in cf.as_completed(futures):
            r, w, e = fut.result()
            counters["reads"] += r
            counters["writes"] += w
            counters["errors"] += e
    elapsed = time.perf_counter() - start

    total_ops = counters["reads"] + counters["writes"]
    return {
        "concurrency": concurrency,
        "duration_s": round(elapsed, 2),
        "read_write_ratio": read_write_ratio,
        "reads": counters["reads"],
        "writes": counters["writes"],
        "errors": counters["errors"],
        "qps": round(total_ops / elapsed, 2) if elapsed > 0 else None,
    }
