"""Unit and integration tests for Part 2 DevOps (Docker, Security, Performance) features."""

from unittest.mock import MagicMock, patch

import httpx

from qa_agent.models import FindingCategory
from qa_agent.testers.container_security import ContainerSecurityTester
from qa_agent.testers.docker_tester import DockerTester
from qa_agent.testers.performance_tester import PerformanceTester
from qa_agent.testers.zap_tester import ZAPTester


def test_docker_tester_static_checks(tmp_path):
    """Test DockerTester checking Dockerfile and docker-compose.yml."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.11\nRUN apt-get update && apt-get install -y git\nCMD ['python']\n", encoding="utf-8")

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  app:\n    privileged: true\n    environment:\n      - DB_PASSWORD='secret123'\n", encoding="utf-8")

    tester = DockerTester(target_dir=str(tmp_path))
    findings = tester.run_all()

    assert len(findings) >= 3
    titles = [f.title for f in findings]
    assert any("Root User" in t for t in titles)
    assert any("Privileges" in t for t in titles)
    assert any("Secret" in t for t in titles)


def test_container_security_tester_missing_trivy():
    """Test ContainerSecurityTester when Trivy is absent."""
    with patch("shutil.which", return_value=None):
        tester = ContainerSecurityTester(target_dir=".")
        findings = tester.run()
        assert len(findings) == 1
        assert "Trivy Container Scanner Not Installed" in findings[0].title


@patch("httpx.Client.request")
def test_zap_tester_security_headers(mock_request):
    """Test ZAPTester for HTTP security headers and cookie flags."""
    mock_res = MagicMock()
    mock_res.headers = {"server": "nginx/1.18.0 (Ubuntu)"}
    mock_res.cookies.jar = []
    mock_request.return_value = mock_res

    tester = ZAPTester()
    findings = tester.check_http_security_headers("https://example.com")

    assert len(findings) >= 5
    categories = {f.category for f in findings}
    assert FindingCategory.SECURITY in categories
    assert any("Content-Security-Policy" in f.title for f in findings)


def test_performance_tester_benchmarks():
    """Test PerformanceTester latency and error rate threshold evaluation."""
    def handler(request):
        return httpx.Response(500, json={"error": "failed"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    tester = PerformanceTester(
        target_url="http://localhost:8000/api",
        duration=0.1,
        max_error_rate=1.0,
        max_p95_ms=10.0,
    )
    findings = tester.benchmark_url("http://localhost:8000/api", client=client)

    assert len(findings) >= 1
    assert any(f.category == FindingCategory.PERFORMANCE for f in findings)
    assert any("High Performance Error Rate" in f.title for f in findings)
