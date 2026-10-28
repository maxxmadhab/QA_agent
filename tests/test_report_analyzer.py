"""Tests for qa_agent/report_analyzer.py — Ingestion, Anti-Hallucination, and LLM Analysis."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.llm_client import LLMProvider, LLMResponse
from qa_agent.models import (
    BrowserResult,
    Finding,
    FindingCategory,
    RootCauseCluster,
    Severity,
    SummaryResult,
    TestSession,
)
from qa_agent.report_analyzer import (
    ReportAnalyzer,
    analyze_report_file,
    ingest_json_report,
    ingest_markdown_report,
    ingest_session,
)


@pytest.fixture
def sample_findings():
    return [
        Finding(
            title="SSL Certificate Expired on Auth Endpoint",
            description="The SSL certificate expired 2 days ago.",
            severity=Severity.CRITICAL,
            category=FindingCategory.NETWORK_ERROR,
            url="https://example.com/api/auth",
        ),
        Finding(
            title="Unresponsive Checkout Submit Button",
            description="Clicking the button throws a javascript type error.",
            severity=Severity.HIGH,
            category=FindingCategory.CONSOLE_ERROR,
            url="https://example.com/checkout",
        ),
    ]


@pytest.fixture
def sample_json_report(tmp_path, sample_findings):
    report_data = {
        "session_id": "test-session-123",
        "pages_tested": 3,
        "total_findings": 2,
        "findings_by_severity": {"critical": 1, "high": 1},
        "findings_by_category": {"network_error": 1, "console_error": 1},
        "findings": [f.to_dict() for f in sample_findings],
        "cross_browser_comparison": {
            "browser_matrix": {
                "chromium": {"status": "passed", "total_findings": 0, "duration_seconds": 1.2},
                "firefox": {"status": "issues_found", "total_findings": 2, "duration_seconds": 1.8},
            },
            "total_common_findings": 0,
        },
        "nl_execution_results": [
            {
                "id": "TC-01",
                "title": "Verify user checkout flow",
                "status": "failed",
                "total_duration_ms": 450,
            }
        ],
    }
    file_path = tmp_path / "qa_report.json"
    file_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    return file_path, report_data


@pytest.fixture
def sample_markdown_report(tmp_path):
    md_content = """# QA AGENT TEST REPORT
Session ID: test-session-md-456
- **Pages Tested:** 2
- **Total Findings:** 2

## Cross-Browser Compatibility Matrix
| Browser | Version | Status | Duration | Findings |
| --- | --- | --- | --- | --- |
| chromium | 120.0 | passed | 2.1s | 0 |
| firefox | 119.0 | issues_found | 3.4s | 2 |

## Findings

### [CRITICAL] SSL Certificate Expired on Auth Endpoint
- **URL:** https://example.com/api/auth
- **Category:** Network Error
- **Description:** The SSL certificate expired 2 days ago.

### [HIGH] Unresponsive Checkout Submit Button
- **URL:** https://example.com/checkout
- **Category:** Console Error
- **Description:** Clicking the button throws a javascript type error.
"""
    file_path = tmp_path / "qa_report.md"
    file_path.write_text(md_content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# Ingestion Tests
# ---------------------------------------------------------------------------

class TestReportIngestion:
    def test_ingest_json_report_file(self, sample_json_report):
        file_path, expected = sample_json_report
        data = ingest_json_report(file_path)

        assert data["session_id"] == "test-session-123"
        assert data["pages_tested"] == 3
        assert data["total_findings"] == 2
        assert len(data["findings"]) == 2
        assert "cross_browser_comparison" in data
        assert len(data["nl_execution_results"]) == 1

    def test_ingest_json_report_dict_and_string(self, sample_json_report):
        _, raw = sample_json_report
        # Dict ingestion
        dict_data = ingest_json_report(raw)
        assert dict_data["session_id"] == "test-session-123"

        # String ingestion
        str_data = ingest_json_report(json.dumps(raw))
        assert str_data["session_id"] == "test-session-123"

    def test_ingest_markdown_report(self, sample_markdown_report):
        data = ingest_markdown_report(sample_markdown_report)

        assert data["pages_tested"] == 2
        assert data["total_findings"] == 2
        assert len(data["findings"]) == 2

        finding_titles = [f["title"] for f in data["findings"]]
        assert "SSL Certificate Expired on Auth Endpoint" in finding_titles
        assert "Unresponsive Checkout Submit Button" in finding_titles

        assert data["cross_browser_comparison"] is not None
        matrix = data["cross_browser_comparison"]["browser_matrix"]
        assert "chromium" in matrix
        assert "firefox" in matrix
        assert matrix["firefox"]["total_findings"] == 2

    def test_ingest_session_instance(self, sample_findings):
        from datetime import datetime
        from qa_agent.models import PageAnalysis

        session = TestSession(session_id="sess-789", start_time=datetime.now())
        page = PageAnalysis(
            url="https://example.com",
            title="Home",
            load_time_ms=100.0,
            interactive_elements=5,
            forms_count=1,
            links_count=2,
            images_count=3,
            findings=[sample_findings[0]],
        )
        session.add_page_analysis(page)
        session.add_finding(sample_findings[1])
        session.browser_results["chromium"] = BrowserResult(browser="chromium", duration_seconds=1.5)
        session.browser_results["firefox"] = BrowserResult(browser="firefox", duration_seconds=2.0)

        data = ingest_session(session)
        assert data["session_id"] == "sess-789"
        assert data["pages_tested"] == 1
        assert data["total_findings"] == 2
        assert len(data["findings"]) == 2
        assert "chromium" in data["browser_results"]
        assert "firefox" in data["browser_results"]


# ---------------------------------------------------------------------------
# Report Analyzer & Anti-Hallucination Tests
# ---------------------------------------------------------------------------

class TestReportAnalyzer:
    def test_analyze_happy_path(self, sample_json_report):
        file_path, _ = sample_json_report
        mock_response = json.dumps({
            "executive_summary": "Overall system stability is compromised by TLS certificate expiry.",
            "cross_browser_analysis": "Firefox exhibited 2 defects while Chromium passed cleanly.",
            "root_cause_clusters": [
                {
                    "label": "Authentication Infrastructure Failure",
                    "finding_titles": ["SSL Certificate Expired on Auth Endpoint"],
                    "root_cause": "Expired SSL cert in load balancer.",
                    "suggested_fix": "Renew and rebind certificate in certbot."
                }
            ],
            "priority_recommendations": [
                "P0: Rotate SSL certificate for /api/auth.",
                "P1: Investigate JavaScript unhandled exception on checkout."
            ],
            "false_positive_candidates": []
        })

        with patch("qa_agent.report_analyzer.create_llm_client") as mock_create:
            mock_client = MagicMock()
            mock_client.complete.return_value = LLMResponse(
                text=mock_response,
                model="test-model",
                provider=LLMProvider.OMNIKEY,
            )
            mock_create.return_value = mock_client

            analyzer = ReportAnalyzer(provider=LLMProvider.OMNIKEY)
            summary = analyzer.analyze(file_path)

            assert isinstance(summary, SummaryResult)
            assert "stability is compromised" in summary.executive_summary
            assert "Firefox exhibited 2 defects" in (summary.cross_browser_analysis or "")
            assert len(summary.root_cause_clusters) == 1
            assert summary.root_cause_clusters[0].label == "Authentication Infrastructure Failure"
            assert summary.root_cause_clusters[0].finding_titles == ["SSL Certificate Expired on Auth Endpoint"]
            assert len(summary.priority_recommendations) == 2

    def test_strict_anti_hallucination_filters_invented_findings(self, sample_json_report):
        file_path, _ = sample_json_report
        # The LLM response includes one genuine finding title and one invented hallucination
        mock_response = json.dumps({
            "executive_summary": "Audit detected critical issues.",
            "cross_browser_analysis": "All browsers affected.",
            "root_cause_clusters": [
                {
                    "label": "Database Outage",
                    "finding_titles": [
                        "SSL Certificate Expired on Auth Endpoint",  # Valid
                        "Invented SQL Injection on User Profile",   # Hallucinated!
                    ],
                    "root_cause": "Misconfiguration.",
                    "suggested_fix": "Fix configuration."
                }
            ],
            "priority_recommendations": ["Fix issues immediately."],
            "false_positive_candidates": []
        })

        with patch("qa_agent.report_analyzer.create_llm_client") as mock_create:
            mock_client = MagicMock()
            mock_client.complete.return_value = LLMResponse(
                text=mock_response,
                model="test-model",
                provider=LLMProvider.OMNIKEY,
            )
            mock_create.return_value = mock_client

            analyzer = ReportAnalyzer(provider=LLMProvider.OMNIKEY)
            summary = analyzer.analyze(file_path)

            # Assert only the real finding title remains in the cluster
            cluster = summary.root_cause_clusters[0]
            assert "SSL Certificate Expired on Auth Endpoint" in cluster.finding_titles
            assert "Invented SQL Injection on User Profile" not in cluster.finding_titles

    def test_markdown_code_block_stripping(self):
        analyzer = ReportAnalyzer()
        text_with_fences = """```json
{
  "executive_summary": "Analysis successful despite markdown wrapper.",
  "cross_browser_analysis": "Single engine evaluated.",
  "root_cause_clusters": [],
  "priority_recommendations": ["Verify logging."],
  "false_positive_candidates": []
}
```"""
        result = analyzer._parse_and_validate(text_with_fences, set())
        assert result.executive_summary == "Analysis successful despite markdown wrapper."

    def test_unparseable_output_graceful_fallback(self):
        analyzer = ReportAnalyzer()
        plain_text = "Sorry, I am an AI and cannot format this as JSON properly."
        result = analyzer._parse_and_validate(plain_text, set())
        assert isinstance(result, SummaryResult)
        assert plain_text in result.executive_summary
        assert len(result.priority_recommendations) > 0

    def test_analyze_report_file_creates_output_artifact(self, sample_json_report):
        file_path, _ = sample_json_report
        mock_response = json.dumps({
            "executive_summary": "Report file processed.",
            "cross_browser_analysis": "None.",
            "root_cause_clusters": [],
            "priority_recommendations": ["Done."],
            "false_positive_candidates": []
        })

        with patch("qa_agent.report_analyzer.create_llm_client") as mock_create:
            mock_client = MagicMock()
            mock_client.complete.return_value = LLMResponse(
                text=mock_response,
                model="test-model",
                provider=LLMProvider.OMNIKEY,
            )
            mock_create.return_value = mock_client

            summary, out_path = analyze_report_file(file_path, provider=LLMProvider.OMNIKEY)
            assert out_path.exists()
            assert out_path.name == f"{file_path.stem}_ai_analysis.json"
            saved_json = json.loads(out_path.read_text(encoding="utf-8"))
            assert saved_json["executive_summary"] == "Report file processed."


# ---------------------------------------------------------------------------
# CLI Integration Tests
# ---------------------------------------------------------------------------

class TestCLIReportAnalysis:
    def test_cli_analyze_report_flag(self, sample_json_report, monkeypatch, capsys):
        file_path, _ = sample_json_report
        mock_summary = SummaryResult(
            executive_summary="CLI executed executive report analysis successfully.",
            cross_browser_analysis="Chromium passed, Firefox failed.",
            root_cause_clusters=[
                RootCauseCluster(
                    label="Network SSL",
                    finding_titles=["SSL Certificate Expired on Auth Endpoint"],
                    root_cause="Cert expiration",
                    suggested_fix="Renew cert",
                )
            ],
            priority_recommendations=["1. Renew SSL"],
        )

        with patch("qa_agent.cli.analyze_report_file", return_value=(mock_summary, file_path)):
            monkeypatch.setattr(
                "sys.argv",
                ["qa-agent", "--analyze-report", str(file_path), "--llm", "omnikey"],
            )
            import qa_agent.cli as cli_mod
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()

            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "AI-POWERED QA REPORT ANALYSIS" in captured.out
            assert "CLI executed executive report analysis successfully." in captured.out
            assert "Chromium passed, Firefox failed." in captured.out
            assert "Network SSL" in captured.out
