"""Timing helpers and percentile math shared by every workload."""
import time
import statistics
from contextlib import contextmanager


class Timer:
    """Collects wall-clock durations (in ms) across repeated calls."""

    def __init__(self):
        self.samples_ms = []

    @contextmanager
    def measure(self):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.samples_ms.append((time.perf_counter() - start) * 1000.0)

    def summary(self) -> dict:
        if not self.samples_ms:
            return {"count": 0, "p50_ms": None, "p95_ms": None, "mean_ms": None}
        data = sorted(self.samples_ms)
        return {
            "count": len(data),
            "p50_ms": round(percentile(data, 50), 3),
            "p95_ms": round(percentile(data, 95), 3),
            "mean_ms": round(statistics.mean(data), 3),
            "min_ms": round(data[0], 3),
            "max_ms": round(data[-1], 3),
        }


def percentile(sorted_data: list, pct: float) -> float:
    """Nearest-rank percentile over already-sorted data."""
    if not sorted_data:
        return float("nan")
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)
