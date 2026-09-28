"""
In-memory metrics store for API monitoring.

Exposes:
  - metrics_store.record_request(...)   called by monitoring middleware
  - metrics_store.record_extraction(...)  called after each PDF job
  - metrics_store.to_json()             for /api/stats endpoint
  - metrics_store.to_prometheus()       for /metrics endpoint (Datadog-compatible)
"""
import threading
import time
from collections import defaultdict, deque
from typing import Any


class MetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()

        # Per-endpoint HTTP counters  { "METHOD:path": count }
        self._req_total: dict[str, int] = defaultdict(int)
        self._err_total: dict[str, int] = defaultdict(int)
        # Rolling window of last 1 000 durations per endpoint
        self._durations: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Extraction-level metrics
        self._extractions_total = 0
        self._extractions_failed = 0
        self._tests_extracted: deque = deque(maxlen=1000)
        self._quality_counts: dict[str, int] = defaultdict(int)  # high/medium/low/failed
        self._guardrail_drops_total = 0

    # ------------------------------------------------------------------
    # Writers (called from middleware / endpoints)
    # ------------------------------------------------------------------

    def record_request(
        self, *, path: str, method: str, status: int, duration_ms: float
    ) -> None:
        key = f"{method}:{path}"
        with self._lock:
            self._req_total[key] += 1
            if status >= 400:
                self._err_total[key] += 1
            self._durations[key].append(duration_ms)

    def record_extraction(
        self,
        *,
        tests_extracted: int,
        quality: str,           # "high" | "medium" | "low" | "failed"
        guardrail_drops: int,
        failed: bool = False,
    ) -> None:
        with self._lock:
            self._extractions_total += 1
            if failed:
                self._extractions_failed += 1
            self._tests_extracted.append(tests_extracted)
            self._quality_counts[quality] += 1
            self._guardrail_drops_total += guardrail_drops

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        with self._lock:
            endpoints = {}
            for key in self._req_total:
                d = list(self._durations[key])
                d_sorted = sorted(d)
                n = len(d_sorted)
                endpoints[key] = {
                    "requests": self._req_total[key],
                    "errors": self._err_total.get(key, 0),
                    "error_rate": round(self._err_total.get(key, 0) / self._req_total[key], 4),
                    "avg_ms": round(sum(d) / n, 2) if n else 0,
                    "p50_ms": round(d_sorted[n // 2], 2) if n else 0,
                    "p95_ms": round(d_sorted[int(n * 0.95)], 2) if n > 1 else 0,
                    "p99_ms": round(d_sorted[int(n * 0.99)], 2) if n > 1 else 0,
                }

            te = list(self._tests_extracted)
            extraction = {
                "total": self._extractions_total,
                "failed": self._extractions_failed,
                "success_rate": round(
                    (self._extractions_total - self._extractions_failed)
                    / max(self._extractions_total, 1),
                    4,
                ),
                "avg_tests_per_report": round(sum(te) / len(te), 2) if te else 0,
                "quality_distribution": dict(self._quality_counts),
                "guardrail_drops_total": self._guardrail_drops_total,
            }

            return {
                "uptime_seconds": round(time.time() - self._started_at),
                "endpoints": endpoints,
                "extraction": extraction,
            }

    def to_prometheus(self) -> str:
        """Prometheus text exposition format — compatible with Datadog agent."""
        lines: list[str] = []

        def line(name: str, labels: dict, value: float, help_: str = "", type_: str = "gauge") -> None:
            if not lines or lines[-1] != f"# HELP {name} {help_}":
                if help_:
                    lines.append(f"# HELP {name} {help_}")
                if type_:
                    lines.append(f"# TYPE {name} {type_}")
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}")

        with self._lock:
            for key, count in self._req_total.items():
                method, path = key.split(":", 1)
                line("http_requests_total", {"method": method, "path": path},
                     count, "Total HTTP requests", "counter")

            for key, count in self._err_total.items():
                method, path = key.split(":", 1)
                line("http_errors_total", {"method": method, "path": path},
                     count, "Total HTTP errors (4xx+5xx)", "counter")

            for key, durations in self._durations.items():
                if not durations:
                    continue
                method, path = key.split(":", 1)
                d = list(durations)
                avg = sum(d) / len(d)
                line("http_duration_ms_avg", {"method": method, "path": path},
                     round(avg, 2), "Average response time in ms")

            line("extractions_total", {}, self._extractions_total,
                 "Total PDF extractions attempted", "counter")
            line("extractions_failed_total", {}, self._extractions_failed,
                 "Total failed PDF extractions", "counter")
            line("guardrail_drops_total", {}, self._guardrail_drops_total,
                 "Lab values dropped by output guardrails", "counter")

            for quality, count in self._quality_counts.items():
                line("extraction_quality_total", {"quality": quality},
                     count, "Extraction quality distribution", "counter")

            te = list(self._tests_extracted)
            if te:
                line("avg_tests_per_report", {}, round(sum(te) / len(te), 2),
                     "Average number of tests extracted per report")

            line("uptime_seconds", {}, round(time.time() - self._started_at),
                 "Process uptime in seconds", "counter")

        return "\n".join(lines)


# Singleton — import this everywhere
metrics_store = MetricsStore()
