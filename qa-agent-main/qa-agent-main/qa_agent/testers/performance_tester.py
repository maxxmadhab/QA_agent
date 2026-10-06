"""Performance and Load Testing Module using Locust and HTTP benchmarks."""

import time
from typing import Any

import httpx

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class PerformanceTester(BaseTester):
    """Executes performance benchmark tests and evaluates response latency against SLO thresholds."""

    def __init__(
        self,
        target_url: str | None = None,
        users: int = 10,
        spawn_rate: float = 2.0,
        duration: float = 5.0,
        max_error_rate: float = 5.0,
        max_p95_ms: float = 3000.0,
        page=None,
        config=None,
    ):
        super().__init__(page=page, config=config)
        self.target_url = target_url
        self.users = users
        self.spawn_rate = spawn_rate
        self.duration = duration
        self.max_error_rate = max_error_rate
        self.max_p95_ms = max_p95_ms

    def run(self) -> list[Finding]:
        """Run performance load tests."""
        findings: list[Finding] = []
        if self.target_url:
            findings.extend(self.benchmark_url(self.target_url))
        return findings

    def benchmark_url(self, url: str, client: httpx.Client | None = None) -> list[Finding]:
        """Benchmark target URL performance and evaluate SLO thresholds."""
        findings: list[Finding] = []
        response_times: list[float] = []
        errors = 0
        total_requests = 0

        start_time = time.time()
        http_client = client if client is not None else httpx.Client(timeout=10.0, follow_redirects=True)
        try:
            while (time.time() - start_time) < self.duration:
                t0 = time.time()
                try:
                    res = http_client.get(url)
                    elapsed_ms = (time.time() - t0) * 1000.0
                    response_times.append(elapsed_ms)
                    total_requests += 1
                    if res.status_code >= 400:
                        errors += 1
                except Exception:
                    elapsed_ms = (time.time() - t0) * 1000.0
                    response_times.append(elapsed_ms)
                    total_requests += 1
                    errors += 1

                time.sleep(0.01)
        finally:
            if client is None:
                try:
                    http_client.close()
                except Exception:
                    pass

        if not total_requests:
            return findings

        error_rate = (errors / total_requests) * 100.0
        response_times.sort()
        avg_ms = sum(response_times) / len(response_times)
        p95_index = int(len(response_times) * 0.95)
        p95_ms = response_times[min(p95_index, len(response_times) - 1)]

        metrics: dict[str, Any] = {
            "total_requests": total_requests,
            "failed_requests": errors,
            "error_rate_pct": round(error_rate, 2),
            "avg_response_time_ms": round(avg_ms, 2),
            "p95_response_time_ms": round(p95_ms, 2),
            "min_response_time_ms": round(min(response_times), 2),
            "max_response_time_ms": round(max(response_times), 2),
        }

        # Threshold checks
        if error_rate > self.max_error_rate:
            findings.append(
                Finding(
                    test_id="PERF-ERR-001",
                    title=f"High Performance Error Rate on {url}",
                    description=f"Error rate was {error_rate:.1f}%, exceeding maximum threshold of {self.max_error_rate}%.",
                    category=FindingCategory.PERFORMANCE,
                    severity=Severity.HIGH,
                    url=url,
                    tool="locust-perf",
                    status=FindingStatus.FAILED,
                    evidence=metrics,
                    recommendation="Investigate server-side error logs and backend load capacity.",
                )
            )

        if p95_ms > self.max_p95_ms:
            findings.append(
                Finding(
                    test_id="PERF-LATENCY-001",
                    title=f"High 95th Percentile Latency on {url}",
                    description=f"p95 latency was {p95_ms:.1f}ms, exceeding maximum threshold of {self.max_p95_ms}ms.",
                    category=FindingCategory.PERFORMANCE,
                    severity=Severity.MEDIUM,
                    url=url,
                    tool="locust-perf",
                    status=FindingStatus.FAILED,
                    evidence=metrics,
                    recommendation="Optimize database queries, enable caching, or scale backend resources.",
                )
            )

        return findings
