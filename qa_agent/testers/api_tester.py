"""API Testing module using HTTPX."""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:
    httpx = None

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class APITester(BaseTester):
    """Tester for HTTP APIs."""

    def __init__(self, base_url: str | None = None, headers: dict[str, str] | None = None, timeout: float = 10.0, page=None, config=None):
        super().__init__(page=page, config=config)
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.default_headers = headers or {}
        self.timeout = timeout

    def run(self) -> list[Finding]:
        """Run standard API health check if base_url is specified."""
        if self.base_url:
            return self.test_endpoint("GET", "/")
        return []

    def test_endpoint(
        self,
        method: str,
        path: str,
        expected_status: int = 200,
        headers: dict[str, str] | None = None,
        json_data: Any | None = None,
        params: dict[str, Any] | None = None,
        test_id: str | None = None,
        description: str | None = None,
    ) -> list[Finding]:
        """Test a single HTTP API endpoint."""
        findings: list[Finding] = []
        full_url = f"{self.base_url}{path}" if self.base_url and path.startswith("/") else (path if path.startswith("http") else f"{self.base_url}/{path}")
        req_headers = {**self.default_headers, **(headers or {})}
        tid = test_id or f"API-{method.upper()}-{expected_status}"

        if httpx is None:
            findings.append(
                Finding(
                    category=FindingCategory.API,
                    title="API Test Skipped (httpx missing)",
                    description="The httpx library is required for API tests. Install it with: pip install httpx",
                    severity=Severity.LOW,
                    status=FindingStatus.FAIL,
                    url=full_url,
                    tool="httpx",
                    remediation="Install httpx using `pip install httpx`",
                )
            )
            return findings

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method=method.upper(),
                    url=full_url,
                    headers=req_headers,
                    json=json_data,
                    params=params,
                )

                if response.status_code != expected_status:
                    findings.append(
                        Finding(
                            test_id=tid,
                            title=f"API Status Code Mismatch on {method.upper()} {path}",
                            description=description or f"Expected HTTP status {expected_status}, but received {response.status_code}.",
                            category=FindingCategory.API,
                            severity=Severity.HIGH if response.status_code >= 500 else Severity.MEDIUM,
                            url=full_url,
                            tool="httpx",
                            status=FindingStatus.FAILED,
                            evidence={
                                "url": full_url,
                                "method": method.upper(),
                                "expected_status": expected_status,
                                "actual_status": response.status_code,
                                "response_body": response.text[:500],
                            },
                            recommendation="Check API implementation and server logs to ensure correct HTTP response status.",
                        )
                    )
        except httpx.TimeoutException:
            findings.append(
                Finding(
                    test_id=tid,
                    title=f"API Timeout on {method.upper()} {path}",
                    description=f"API request timed out after {self.timeout}s.",
                    category=FindingCategory.API,
                    severity=Severity.HIGH,
                    url=full_url,
                    tool="httpx",
                    status=FindingStatus.FAILED,
                    evidence={"url": full_url, "method": method.upper(), "timeout_seconds": self.timeout},
                    recommendation="Optimize endpoint performance or adjust timeout settings.",
                )
            )
        except Exception as e:
            findings.append(
                Finding(
                    test_id=tid,
                    title=f"API Request Error on {method.upper()} {path}",
                    description=f"API request failed with exception: {str(e)}",
                    category=FindingCategory.API,
                    severity=Severity.HIGH,
                    url=full_url,
                    tool="httpx",
                    status=FindingStatus.FAILED,
                    evidence={"url": full_url, "method": method.upper(), "error": str(e)},
                    recommendation="Ensure the API server is running and reachable.",
                )
            )

        return findings
