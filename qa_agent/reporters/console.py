"""Console reporter for real-time output."""

import sys
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import Finding, TestSession


class ConsoleReporter(BaseReporter):
    """Outputs test results to the console in real-time."""

    def __init__(self, output_dir: str = "./qa_reports", use_colors: bool = True):
        super().__init__(output_dir)
        self.use_colors = use_colors and sys.stdout.isatty()
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(errors="replace")
            except Exception:
                pass

    def _color(self, text: str, color_code: str) -> str:
        """Apply ANSI color code to text."""
        if not self.use_colors:
            return text
        return f"\033[{color_code}m{text}\033[0m"

    def _severity_color(self, severity: str) -> str:
        """Get color for severity."""
        return {
            "critical": "91",  # Red
            "high": "93",      # Yellow
            "medium": "33",    # Dark yellow
            "low": "94",       # Blue
            "info": "90",      # Gray
        }.get(severity, "0")

    def generate(self, session: "TestSession") -> str:
        """Generate console output for the complete session."""
        self._print_header(session)
        self._print_summary(session)
        self._print_cross_browser_summary(session)
        self._print_nl_test_cases_summary(session)
        self._print_findings(session)
        self._print_footer(session)
        return "Console output complete"

    def _print_nl_test_cases_summary(self, session: "TestSession"):
        """Print natural language test cases and step execution outcomes."""
        if not getattr(session, "nl_execution_results", None):
            return
        print(f"\n{self._color('🧪 NATURAL LANGUAGE EXECUTABLE TEST CASES', '1;95')}")
        print("-" * 65)
        for tc in session.nl_execution_results:
            status_color = "92" if tc.get("status") == "passed" else ("93" if tc.get("status") == "failed" else "91")
            status_badge = self._color(f"[{tc.get('status', 'UNKNOWN').upper()}]", status_color)
            print(f"  {status_badge} [{tc.get('id')}] {tc.get('title')} ({tc.get('total_duration_ms', 0):.1f}ms)")
            for s in tc.get("step_results", []):
                s_icon = "✓" if s.get("status") == "passed" else "✗"
                print(f"      {s_icon} Step {s.get('step_index')}: {s.get('action')} {s.get('description', '')} ({s.get('duration_ms', 0):.1f}ms)")
            for a in tc.get("assertion_results", []):
                a_icon = "✓" if a.get("status") == "passed" else "✗"
                print(f"      {a_icon} Assert {a.get('assertion_index')}: {a.get('type')} expected={a.get('expected_value')} got={a.get('actual_value')} ({a.get('duration_ms', 0):.1f}ms)")


    def _print_cross_browser_summary(self, session: "TestSession"):
        """Print cross-browser comparison matrix if multiple browsers were tested."""
        if not getattr(session, "browser_results", None) or len(session.browser_results) <= 1:
            return

        comparison = session.get_cross_browser_comparison()
        print(f"\n{self._color('🌐 CROSS-BROWSER TESTING COMPARISON', '1;96')}")
        print("-" * 65)

        print(f"  {'Browser':<12} {'Version':<14} {'Status':<16} {'Duration':<10} {'Findings':<10}")
        print(f"  {'-'*10:<12} {'-'*12:<14} {'-'*14:<16} {'-'*8:<10} {'-'*8:<10}")
        for b, info in comparison["browser_matrix"].items():
            version = info.get("version") or "N/A"
            raw_status = str(info.get("status", "unknown")).upper()
            status_color = "92" if raw_status == "PASSED" else ("93" if raw_status == "ISSUES_FOUND" else "91")
            dur = f"{info.get('duration_seconds', 0.0):.1f}s"
            findings_count = str(info.get("total_findings", 0))
            status_str = f"{raw_status} (err)" if info.get("error") else raw_status
            colored_status = self._color(status_str, status_color)
            print(f"  {b.title():<12} {version:<14} {colored_status:<24} {dur:<10} {findings_count:<10}")

        common_count = comparison["total_common_findings"]
        print(f"\n  {self._color('Common Issues Across All Browsers:', '1')} {common_count}")
        for f in comparison["common_findings"][:5]:
            print(f"    • [{f['severity'].upper()}] {f['title']} ({f.get('url', '')})")
        if common_count > 5:
            print(f"    ... and {common_count - 5} more common issues")

        specific = comparison["browser_specific_findings"]
        if specific:
            print(f"\n  {self._color('Browser-Specific Issues:', '1')}")
            for b, items in specific.items():
                print(f"    [{b.upper()}] ({len(items)} issues unique to this browser):")
                for f in items[:3]:
                    print(f"      - [{f['severity'].upper()}] {f['title']}")
                if len(items) > 3:
                    print(f"      ... and {len(items) - 3} more")

    def print_finding(self, finding: "Finding"):
        """Print a single finding in real-time."""
        emoji = self._severity_emoji(finding.severity.value)
        cat_emoji = self._category_emoji(finding.category.value)
        severity = finding.severity.value.upper()
        color = self._severity_color(finding.severity.value)

        print(f"\n{emoji} {self._color(f'[{severity}]', color)} {cat_emoji} {finding.title}")
        print(f"   {finding.description}")
        if finding.url:
            print(f"   📍 {self._color(finding.url, '90')}")

    def print_progress(self, message: str):
        """Print progress message."""
        print(f"  → {message}")

    def print_error(self, message: str) -> None:
        """Print an error message in red."""
        print(f"  {self._color('✗ ERROR:', '91')} {message}")

    def print_warning(self, message: str) -> None:
        """Print a test reliability warning."""
        print(f"  ⚠  {self._color('WARNING:', '93')} {message}")

    def print_page_start(self, url: str):
        """Print when starting to test a new page."""
        print(f"\n{'='*60}")
        print(f"🔍 Testing: {self._color(url, '96')}")
        print(f"{'='*60}")

    def print_test_category(self, category: str):
        """Print test category being run."""
        print(f"  📋 Running {category} tests...")

    def _print_header(self, session: "TestSession"):
        """Print report header."""
        print("\n" + "=" * 70)
        print(self._color("  QA AGENT TEST REPORT", "1;96"))
        print("=" * 70)
        print(f"  Session ID: {session.session_id}")
        print(f"  Started:    {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            print(f"  Completed:  {session.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Duration:   {duration:.1f} seconds")
        print(f"  Mode:       {session.config_summary.get('mode', 'N/A')}")
        print("=" * 70)

    def _print_summary(self, session: "TestSession"):
        """Print summary statistics."""
        print(f"\n{self._color('📊 SUMMARY', '1;97')}")
        print("-" * 40)
        print(f"  Pages tested: {len(session.pages_tested)}")
        print(f"  Total findings: {session.total_findings}")

        if session.findings_by_severity:
            print(f"\n  {self._color('By Severity:', '1')}")
            for severity in ["critical", "high", "medium", "low", "info"]:
                count = session.findings_by_severity.get(severity, 0)
                if count > 0:
                    emoji = self._severity_emoji(severity)
                    color = self._severity_color(severity)
                    print(f"    {emoji} {self._color(severity.upper(), color)}: {count}")

        if session.findings_by_category:
            print(f"\n  {self._color('By Category:', '1')}")
            for category, count in sorted(session.findings_by_category.items(), key=lambda x: -x[1]):
                if count > 0:
                    emoji = self._category_emoji(category)
                    print(f"    {emoji} {category.replace('_', ' ').title()}: {count}")

    def _print_findings(self, session: "TestSession"):
        """Print all findings grouped by severity."""
        findings = session.get_all_findings()

        if not findings:
            if not session.pages_tested:
                print(f"\n{self._color('⚠️  No pages were successfully tested!', '93')}")
            else:
                print(f"\n{self._color('✅ No issues found!', '92')}")
            return

        print(f"\n{self._color('📋 FINDINGS', '1;97')}")
        print("-" * 40)

        # Group by severity
        severity_order = ["critical", "high", "medium", "low", "info"]
        grouped: dict[str, list] = {}
        for finding in findings:
            sev = finding.severity.value
            if sev not in grouped:
                grouped[sev] = []
            grouped[sev].append(finding)

        for severity in severity_order:
            if severity not in grouped:
                continue

            color = self._severity_color(severity)
            emoji = self._severity_emoji(severity)
            print(f"\n{emoji} {self._color(severity.upper() + ' SEVERITY', f'1;{color}')}")

            for i, finding in enumerate(grouped[severity], 1):
                cat_emoji = self._category_emoji(finding.category.value)
                tool_tag = f" [{finding.tool}]" if finding.tool else ""
                test_id_tag = f" ({finding.test_id})" if finding.test_id else ""
                print(f"\n  {i}. {cat_emoji} {self._color(finding.title, '1')}{tool_tag}{test_id_tag}")
                print(f"     {finding.description}")

                if finding.url:
                    print(f"     📍 URL: {self._color(finding.url, '90')}")
                if finding.element_selector:
                    print(f"     🎯 Selector: {finding.element_selector}")
                if finding.expected_behavior:
                    print(f"     ✓ Expected: {finding.expected_behavior}")
                if finding.actual_behavior:
                    print(f"     ✗ Actual: {finding.actual_behavior}")
                if finding.evidence:
                    print(f"     🔍 Evidence: {finding.evidence}")
                if finding.recommendation:
                    print(f"     💡 Recommendation: {finding.recommendation}")
                if finding.steps_to_reproduce:
                    print(f"     📝 Steps: {', '.join(finding.steps_to_reproduce)}")

    def _print_footer(self, session: "TestSession"):
        """Print report footer."""
        print("\n" + "=" * 70)

        if not session.pages_tested:
            print(self._color("  ⚠️  No pages were successfully tested — check URLs and connectivity", "93"))
        elif session.total_findings == 0:
            print(self._color("  ✅ All tests passed with no issues found!", "92"))
        else:
            critical_high = session.findings_by_severity.get("critical", 0) + session.findings_by_severity.get("high", 0)
            if critical_high > 0:
                print(self._color(f"  ⚠️  {critical_high} critical/high severity issues require attention", "91"))
            else:
                print(self._color(f"  ℹ️  {session.total_findings} issues found, none critical", "93"))

        if session.recording_path:
            print(f"  📹 Recording saved: {session.recording_path}")

        print("=" * 70 + "\n")
