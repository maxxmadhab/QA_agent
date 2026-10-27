"""Unit and integration tests for Feature 1: Cross-Browser Testing."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

from qa_agent.agent import QAAgent
from qa_agent.cli import main
from qa_agent.config import TestConfig, TestMode
from qa_agent.models import (
    BrowserResult,
    Finding,
    FindingCategory,
    FindingStatus,
    PageAnalysis,
    Severity,
    TestSession,
)
from qa_agent.reporters import ConsoleReporter, MarkdownReporter
from qa_agent.web.server import _build_config


class TestCrossBrowserConfig:
    """Test browser configuration parsing and normalization in TestConfig."""

    def test_default_browsers(self):
        config = TestConfig(urls=["https://example.com"])
        assert config.browsers == ["chromium"]
        assert config.browser_type == "chromium"

    def test_custom_valid_browsers(self):
        config = TestConfig(
            urls=["https://example.com"],
            browsers=["chromium", "firefox", "webkit"],
        )
        assert config.browsers == ["chromium", "firefox", "webkit"]
        assert config.browser_type == "chromium"

    def test_browser_normalization_case_and_deduplication(self):
        config = TestConfig(
            urls=["https://example.com"],
            browsers=["Chromium", "FIREFOX", "chromium", "invalid_browser"],
        )
        assert config.browsers == ["chromium", "firefox"]

    def test_empty_browsers_fallback(self):
        config = TestConfig(urls=["https://example.com"], browsers=[])
        assert config.browsers == ["chromium"]


class TestCrossBrowserModels:
    """Test data models and cross-browser comparison matrix logic."""

    def test_finding_browser_metadata(self):
        finding = Finding(
            title="Broken Button",
            description="Button does not respond to clicks",
            category=FindingCategory.FUNCTIONAL,
            severity=Severity.HIGH,
            url="https://example.com",
            browser="firefox",
            browser_version="155.0",
        )
        d = finding.to_dict()
        assert d["browser"] == "firefox"
        assert d["browser_version"] == "155.0"

    def test_browser_result_to_dict(self):
        b_res = BrowserResult(
            browser="chromium",
            browser_version="153.0",
            status="passed",
            duration_seconds=3.456,
            pages_tested=["https://example.com"],
            total_findings=0,
        )
        d = b_res.to_dict()
        assert d["browser"] == "chromium"
        assert d["browser_version"] == "153.0"
        assert d["status"] == "passed"
        assert d["duration_seconds"] == 3.46
        assert d["pages_tested"] == ["https://example.com"]

    def test_cross_browser_comparison_common_and_specific(self):
        session = TestSession(
            session_id="test1234",
            start_time=datetime.now(),
        )

        # Common finding (appears on both Chromium and Firefox)
        f_common_c = Finding(
            title="Missing alt text",
            description="Logo image missing alt attribute",
            category=FindingCategory.ACCESSIBILITY,
            severity=Severity.MEDIUM,
            url="https://example.com/home",
            browser="chromium",
        )
        f_common_f = Finding(
            title="Missing alt text",
            description="Logo image missing alt attribute",
            category=FindingCategory.ACCESSIBILITY,
            severity=Severity.MEDIUM,
            url="https://example.com/home",
            browser="firefox",
        )

        # Chromium-specific finding
        f_chromium_only = Finding(
            title="CSS Grid Layout Bug",
            description="Layout misaligned on Chromium",
            category=FindingCategory.FUNCTIONAL,
            severity=Severity.LOW,
            url="https://example.com/home",
            browser="chromium",
        )

        # Firefox-specific finding
        f_firefox_only = Finding(
            title="Scrollbar Overflow Issue",
            description="Horizontal scrollbar appears in Firefox",
            category=FindingCategory.FUNCTIONAL,
            severity=Severity.LOW,
            url="https://example.com/home",
            browser="firefox",
        )

        session.browser_results["chromium"] = BrowserResult(
            browser="chromium",
            browser_version="153.0",
            status="issues_found",
            duration_seconds=2.0,
            pages_tested=["https://example.com/home"],
            total_findings=2,
            findings=[f_common_c, f_chromium_only],
        )

        session.browser_results["firefox"] = BrowserResult(
            browser="firefox",
            browser_version="155.0",
            status="issues_found",
            duration_seconds=2.5,
            pages_tested=["https://example.com/home"],
            total_findings=2,
            findings=[f_common_f, f_firefox_only],
        )

        comparison = session.get_cross_browser_comparison()
        assert comparison["tested_browsers"] == ["chromium", "firefox"]
        assert len(comparison["successful_browsers"]) == 2
        assert comparison["total_common_findings"] == 1
        assert comparison["common_findings"][0]["title"] == "Missing alt text"
        assert set(comparison["common_findings"][0]["affected_browsers"]) == {"chromium", "firefox"}

        # Check browser-specific breakdown
        specific = comparison["browser_specific_findings"]
        assert len(specific["chromium"]) == 1
        assert specific["chromium"][0]["title"] == "CSS Grid Layout Bug"
        assert len(specific["firefox"]) == 1
        assert specific["firefox"][0]["title"] == "Scrollbar Overflow Issue"

    def test_cross_browser_with_unavailable_browser(self):
        session = TestSession(
            session_id="test5678",
            start_time=datetime.now(),
        )
        session.browser_results["chromium"] = BrowserResult(
            browser="chromium",
            browser_version="153.0",
            status="passed",
            duration_seconds=1.2,
            pages_tested=["https://example.com"],
            total_findings=0,
            findings=[],
        )
        session.browser_results["webkit"] = BrowserResult(
            browser="webkit",
            browser_version=None,
            status="unavailable",
            error_message="BrowserType.launch: Executable doesn't exist",
            duration_seconds=0.1,
            pages_tested=[],
            total_findings=0,
            findings=[],
        )

        comparison = session.get_cross_browser_comparison()
        assert comparison["tested_browsers"] == ["chromium", "webkit"]
        assert comparison["successful_browsers"] == ["chromium"]
        assert comparison["browser_matrix"]["webkit"]["status"] == "unavailable"
        assert "Executable doesn't exist" in comparison["browser_matrix"]["webkit"]["error"]


class TestCrossBrowserExecution:
    """Test QAAgent cross-browser execution lifecycle and failure isolation."""

    def test_unavailable_browser_does_not_abort_other_browsers(self, tmp_path):
        """Verify that if one browser fails to launch, the other browser still succeeds."""
        config = TestConfig(
            urls=["https://example.com"],
            browsers=["chromium", "webkit"],
            output_dir=str(tmp_path),
        )

        # Mock playwright factory
        mock_chromium = MagicMock()
        mock_chromium_browser = MagicMock()
        mock_chromium_browser.version = "153.0"
        mock_chromium.launch.return_value = mock_chromium_browser

        mock_webkit = MagicMock()
        mock_webkit.launch.side_effect = Exception("Executable doesn't exist for webkit")

        mock_pw = MagicMock()
        mock_pw.chromium = mock_chromium
        mock_pw.webkit = mock_webkit

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_pw

        agent = QAAgent(config, playwright_factory=mock_factory)

        # Mock page testing so chromium succeeds
        mock_context = MagicMock()
        mock_page = MagicMock()
        agent._new_context_page = MagicMock(return_value=(mock_context, mock_page))
        agent._test_page = MagicMock(side_effect=lambda url: agent.session.add_page_analysis(
            PageAnalysis(url=url, title="Test Page", load_time_ms=100, interactive_elements=5, forms_count=0, links_count=0, images_count=0)
        ))

        session = agent.run()

        # Both browsers must be recorded
        assert "chromium" in session.browser_results
        assert "webkit" in session.browser_results

        # Chromium succeeded
        assert session.browser_results["chromium"].status == "passed"
        assert session.browser_results["chromium"].browser_version == "153.0"
        assert len(session.browser_results["chromium"].pages_tested) == 1

        # WebKit marked unavailable
        assert session.browser_results["webkit"].status == "unavailable"
        assert "Executable doesn't exist" in session.browser_results["webkit"].error_message

        # Overall session completed without crashing
        assert len(session.pages_tested) == 1
        assert session.end_time is not None

    def test_independent_screenshot_directories_per_browser(self, tmp_path):
        """Verify that screenshots are stored under isolated subdirectories per browser."""
        config = TestConfig(
            urls=["https://example.com"],
            browsers=["chromium", "firefox"],
            output_dir=str(tmp_path),
        )

        mock_browser = MagicMock()
        mock_browser.version = "100.0"
        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_pw.firefox.launch.return_value = mock_browser

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_pw

        agent = QAAgent(config, playwright_factory=mock_factory)
        agent._new_context_page = MagicMock(return_value=(MagicMock(), MagicMock()))
        agent._test_page = MagicMock()

        session = agent.run()
        assert "chromium" in session.browser_results
        assert "firefox" in session.browser_results


class TestCrossBrowserReportersAndWeb:
    """Test console and markdown reporters and web config builder for cross-browser."""

    def test_console_reporter_renders_cross_browser_summary(self, capsys):
        session = TestSession(
            session_id="cb_test",
            start_time=datetime.now(),
        )
        session.browser_results["chromium"] = BrowserResult(
            browser="chromium",
            browser_version="153.0",
            status="passed",
            duration_seconds=1.5,
        )
        session.browser_results["firefox"] = BrowserResult(
            browser="firefox",
            browser_version="155.0",
            status="passed",
            duration_seconds=1.8,
        )

        reporter = ConsoleReporter(use_colors=False)
        reporter.generate(session)

        captured = capsys.readouterr().out
        assert "CROSS-BROWSER TESTING COMPARISON" in captured
        assert "Chromium" in captured
        assert "Firefox" in captured

    def test_markdown_reporter_renders_matrix_table(self):
        session = TestSession(
            session_id="cb_md",
            start_time=datetime.now(),
        )
        session.browser_results["chromium"] = BrowserResult(
            browser="chromium",
            browser_version="153.0",
            status="passed",
            duration_seconds=2.1,
            findings=[],
        )
        session.browser_results["firefox"] = BrowserResult(
            browser="firefox",
            browser_version="155.0",
            status="issues_found",
            duration_seconds=2.4,
            total_findings=1,
            findings=[
                Finding(
                    title="Font rendering mismatch",
                    description="Font kerning differs",
                    category=FindingCategory.VISUAL_ISSUE,
                    severity=Severity.LOW,
                    url="https://example.com",
                    browser="firefox",
                )
            ],
        )

        reporter = MarkdownReporter(output_dir="./dummy")
        content = "\n".join(reporter._format_cross_browser(session))
        assert "Cross-Browser Compatibility Matrix" in content
        assert "| Chromium | 153.0 | PASSED | 2.1s | 0 |" in content
        assert "| Firefox | 155.0 | ISSUES_FOUND | 2.4s | 1 |" in content
        assert "Browser-Specific Issues" in content
        assert "Font rendering mismatch" in content

    def test_web_build_config_parses_browsers(self):
        body = {
            "urls": ["https://example.com"],
            "browsers": ["chromium", "firefox", "webkit"],
        }
        cfg = _build_config(body)
        assert cfg.browsers == ["chromium", "firefox", "webkit"]

    def test_web_build_config_defaults_browsers(self):
        body = {"urls": ["https://example.com"]}
        cfg = _build_config(body)
        assert cfg.browsers == ["chromium"]
