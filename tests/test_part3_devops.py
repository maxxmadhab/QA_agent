"""Unit and integration tests for Part 3 DevOps & Reporting features."""

import json
from datetime import datetime

from qa_agent.cli import _should_fail_for_severity
from qa_agent.models import (
    Finding,
    FindingCategory,
    FindingStatus,
    PageAnalysis,
    Severity,
    TestSession,
)
from qa_agent.reporters.json_reporter import JSONReporter
from qa_agent.reporters.markdown import MarkdownReporter
from qa_agent.summarizer import _serialize_session
from qa_agent.web.server import _build_config


def test_should_fail_for_severity():
    findings = {"high": 1, "medium": 2}
    assert _should_fail_for_severity(findings, "high") is True
    assert _should_fail_for_severity(findings, "critical") is False
    assert _should_fail_for_severity(findings, "medium") is True
    assert _should_fail_for_severity(findings, None) is False


def test_summarizer_serialize_session_devops_fields():
    session = TestSession(
        session_id="test-session-123",
        start_time=datetime.now(),
        config_summary={"mode": "focused", "urls": ["https://example.com"]},
    )
    page = PageAnalysis(
        url="https://example.com",
        title="Example Page",
        load_time_ms=120.0,
        interactive_elements=5,
        forms_count=1,
        links_count=2,
        images_count=1,
    )
    finding = Finding(
        test_id="SEC-001",
        tool="ZAPTester",
        status=FindingStatus.FAILED,
        title="Missing CSP Header",
        severity=Severity.HIGH,
        category=FindingCategory.SECURITY,
        description="Content-Security-Policy header is missing",
        evidence="Header missing in response",
        recommendation="Add Content-Security-Policy header",
        url="https://example.com",
    )
    page.findings.append(finding)
    session.add_page_analysis(page)

    serialized_str = _serialize_session(session)
    data = json.loads(serialized_str)

    assert data["total_findings"] == 1
    f_dict = data["findings"][0]
    assert f_dict["test_id"] == "SEC-001"
    assert f_dict["tool"] == "ZAPTester"
    assert f_dict["evidence"] == "Header missing in response"
    assert f_dict["recommendation"] == "Add Content-Security-Policy header"


def test_reporters_render_devops_fields(tmp_path):
    session = TestSession(
        session_id="devops-report-session",
        start_time=datetime.now(),
        config_summary={"mode": "focused", "urls": ["https://example.com"]},
    )
    page = PageAnalysis(
        url="https://example.com",
        title="Example Page",
        load_time_ms=100.0,
        interactive_elements=2,
        forms_count=0,
        links_count=1,
        images_count=0,
    )
    finding = Finding(
        test_id="DOCKER-001",
        tool="DockerTester",
        status=FindingStatus.FAILED,
        title="Root User Execution",
        severity=Severity.HIGH,
        category=FindingCategory.CONTAINER,
        description="Container runs as root",
        evidence="No USER instruction found",
        recommendation="Add USER appuser to Dockerfile",
        url="https://example.com",
    )
    page.findings.append(finding)
    session.add_page_analysis(page)

    # Test MarkdownReporter
    md_reporter = MarkdownReporter(output_dir=str(tmp_path))
    md_file = md_reporter.generate(session)
    md_content = (tmp_path / md_file).read_text(encoding="utf-8")
    assert "DOCKER-001" in md_content
    assert "DockerTester" in md_content
    assert "No USER instruction found" in md_content

    # Test JSONReporter
    json_reporter = JSONReporter(output_dir=str(tmp_path))
    json_file = json_reporter.generate(session)
    json_content = (tmp_path / json_file).read_text(encoding="utf-8")
    json_data = json.loads(json_content)
    assert json_data["findings"][0]["test_id"] == "DOCKER-001"
    assert json_data["findings"][0]["tool"] == "DockerTester"


def test_web_server_build_config_devops_flags():
    body = {
        "urls": ["https://example.com"],
        "mode": "explore",
        "test_api": True,
        "test_docker": True,
        "test_container_security": True,
        "test_web_security": True,
        "test_performance": True,
        "locust_users": 25,
        "locust_duration": 10.0,
    }
    config = _build_config(body)
    assert config.urls == ["https://example.com"]
    assert config.enable_api_tests is True
    assert config.enable_docker_tests is True
    assert config.enable_container_security is True
    assert config.enable_web_security is True
    assert config.enable_performance_tests is True
    assert config.locust_users == 25
    assert config.locust_duration == 10.0
