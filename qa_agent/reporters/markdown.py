"""Markdown report generator."""

import os
import re
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import Finding, SummaryResult, TestSession


class MarkdownReporter(BaseReporter):
    """Generates Markdown format reports."""

    def generate(self, session: "TestSession") -> str:
        """Generate Markdown report and save to file."""
        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = session.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"qa_report_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        content = self._build_report(session)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.write("\n")

        return filepath

    def _build_report(self, session: "TestSession") -> str:
        """Build the complete Markdown report."""
        lines = []

        # Header
        lines.append("# QA Agent Test Report")
        lines.append("")
        lines.append(f"**Session ID:** `{session.session_id}`")
        lines.append(f"**Date:** {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            lines.append(f"**Duration:** {duration:.1f} seconds")

        lines.append(f"**Mode:** {session.config_summary.get('mode', 'N/A')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Pages Tested:** {len(session.pages_tested)}")
        lines.append(f"- **Total Findings:** {session.total_findings}")
        lines.append("")

        # Severity breakdown
        if session.findings_by_severity:
            lines.append("### Findings by Severity")
            lines.append("")
            lines.append("| Severity | Count |")
            lines.append("| --- | --- |")
            for severity in ["critical", "high", "medium", "low", "info"]:
                count = session.findings_by_severity.get(severity, 0)
                if count > 0:
                    emoji = self._severity_emoji(severity)
                    lines.append(f"| {emoji} {severity.upper()} | {count} |")
            lines.append("")

        # Category breakdown
        if session.findings_by_category:
            lines.append("### Findings by Category")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("| --- | --- |")
            for category, count in sorted(session.findings_by_category.items(), key=lambda x: -x[1]):
                if count > 0:
                    emoji = self._category_emoji(category)
                    cat_name = category.replace("_", " ").title()
                    lines.append(f"| {emoji} {cat_name} | {count} |")
            lines.append("")

        # Cross-browser testing section
        if getattr(session, "browser_results", None) and len(session.browser_results) > 1:
            lines.extend(self._format_cross_browser(session))

        # AI summary section
        if session.summary:
            lines.extend(self._format_summary(session.summary))

        # Test reliability warnings
        plan_warnings = session.config_summary.get("plan_warnings", [])
        if plan_warnings:
            lines.append("## ⚠ Test Reliability Warnings")
            lines.append("")
            lines.append(
                "> These warnings were detected before execution. Results may include "
                "false passes where the plan cannot meaningfully verify the intended behavior."
            )
            lines.append("")
            for w in plan_warnings:
                lines.append(f"- {w}")
            lines.append("")

        # Pages tested
        lines.append("## Pages Tested")
        lines.append("")
        for page in session.pages_tested:
            finding_count = len(page.findings)
            label = page.title or page.url
            if finding_count == 0:
                lines.append(f"- [{label}]({page.url}) - ✅")
            else:
                status = f"⚠️ {finding_count} {'issue' if finding_count == 1 else 'issues'}"
                lines.append("<details>")
                lines.append(f"<summary><a href=\"{page.url}\">{label}</a> - {status}</summary>")
                lines.append("")
                for finding in page.findings:
                    lines.append(f"- {finding.title}")
                lines.append("")
                lines.append("</details>")
        lines.append("")

        # Natural Language Test Cases
        if getattr(session, "nl_execution_results", None):
            lines.append("## Natural Language Executable Test Cases")
            lines.append("")
            for tc in session.nl_execution_results:
                status_emoji = "✅" if tc.get("status") == "passed" else ("⚠️" if tc.get("status") == "failed" else "❌")
                lines.append(f"### {status_emoji} [{tc.get('id')}] {tc.get('title')}")
                lines.append(f"- **Status:** `{tc.get('status', '').upper()}`")
                lines.append(f"- **Total Duration:** {tc.get('total_duration_ms', 0):.1f}ms")
                lines.append("")
                if tc.get("step_results"):
                    lines.append("#### Action Steps")
                    lines.append("| # | Action | Target / Details | Status | Duration |")
                    lines.append("| --- | --- | --- | --- | --- |")
                    for s in tc.get("step_results", []):
                        s_status = f"`{s.get('status', '').upper()}`"
                        details = s.get("description") or f"{s.get('target', '')} {s.get('value', '')}".strip()
                        lines.append(f"| {s.get('step_index')} | `{s.get('action')}` | {details} | {s_status} | {s.get('duration_ms', 0):.1f}ms |")
                    lines.append("")
                if tc.get("assertion_results"):
                    lines.append("#### Assertions")
                    lines.append("| # | Type | Target | Expected | Actual | Status |")
                    lines.append("| --- | --- | --- | --- | --- | --- |")
                    for a in tc.get("assertion_results", []):
                        a_status = f"`{a.get('status', '').upper()}`"
                        lines.append(f"| {a.get('assertion_index')} | `{a.get('type')}` | `{a.get('target', '-')}` | {a.get('expected_value', '-')} | {a.get('actual_value', '-')} | {a_status} |")
                    lines.append("")

        # Detailed findings

        findings = session.get_deduplicated_findings()
        raw_count = session.total_findings
        dedup_count = len(findings)
        if findings:
            lines.append("## Detailed Findings")
            lines.append("")
            if dedup_count < raw_count:
                lines.append(
                    f"> **Note:** {raw_count} raw findings were consolidated into "
                    f"{dedup_count} unique issues by grouping identical problems "
                    f"across URL variants (e.g. `/widget/{{id}}`)."
                )
                lines.append("")

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

                emoji = self._severity_emoji(severity)
                lines.append(f"### {emoji} {severity.upper()} Severity")
                lines.append("")

                for i, finding in enumerate(grouped[severity], 1):
                    cat_emoji = self._category_emoji(finding.category.value)
                    lines.extend(self._format_finding(finding, i, cat_emoji))
                    lines.append("")
        elif not session.pages_tested:
            lines.append("## ⚠️ No Pages Tested")
            lines.append("")
            lines.append("No pages were successfully loaded. Check URLs and connectivity.")
            lines.append("")
        else:
            lines.append("## ✅ No Issues Found")
            lines.append("")
            lines.append("All tests passed without detecting any issues.")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Generated by QA Agent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        if session.recording_path:
            lines.append("")
            lines.append(f"📹 **Session Recording:** `{session.recording_path}`")

        return "\n".join(lines)

    def _format_summary(self, summary: "SummaryResult") -> list[str]:
        """Format the AI summary block."""
        lines: list[str] = []

        lines.append("## AI Analysis")
        lines.append("")
        lines.append("> *Generated by LLM after the test run. Treat as advisory — verify before acting.*")
        lines.append("")

        lines.append("### Executive Summary")
        lines.append("")
        lines.append(summary.executive_summary)
        lines.append("")

        if summary.priority_recommendations:
            lines.append("### Priority Recommendations")
            lines.append("")
            for rec in summary.priority_recommendations:
                lines.append(f"1. {rec}")
            lines.append("")

        if summary.root_cause_clusters:
            lines.append("### Root Cause Clusters")
            lines.append("")
            for cluster in summary.root_cause_clusters:
                lines.append(f"#### {cluster.label}")
                lines.append("")
                lines.append(f"**Root cause:** {cluster.root_cause}")
                lines.append("")
                lines.append(f"**Suggested fix:** {cluster.suggested_fix}")
                lines.append("")
                lines.append("**Related findings:**")
                for title in cluster.finding_titles:
                    lines.append(f"- {title}")
                lines.append("")

        if summary.false_positive_candidates:
            lines.append("### Possible False Positives")
            lines.append("")
            lines.append(
                "> These findings may be test artifacts rather than real bugs — review before filing."
            )
            lines.append("")
            for candidate in summary.false_positive_candidates:
                lines.append(f"- {candidate}")
            lines.append("")

        return lines

    def _escape_html_tags(self, text: str) -> str:
        """Wrap HTML tags in backticks so they render correctly in markdown previews.

        Note: [^>]* in the attribute group stops at the first '>', so attribute values
        containing '>' (e.g. class="a > b") will cause partial wrapping. Acceptable
        given AI-generated input is unlikely to hit this; a full fix would require
        matching quoted attribute values explicitly.
        """
        return re.sub(r'(?<!`)</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?>(?!`)', r'`\g<0>`', text)

    def _format_finding(self, finding: "Finding", index: int, emoji: str) -> list[str]:
        """Format a single finding as Markdown, with screenshot paths relative to the report file."""
        lines = []

        header = f"#### {index}. {emoji} {finding.title}"
        if finding.test_id:
            header += f" `{finding.test_id}`"
        lines.append(header)
        lines.append("")
        if finding.tool:
            lines.append(f"**Tool / Module:** `{finding.tool}`")
            lines.append("")
        lines.append(f"**Description:** {self._escape_html_tags(finding.description)}")
        lines.append("")

        if finding.url:
            if finding.affected_urls:
                lines.append(f"**URL Pattern:** `{finding.url}` — affects {len(finding.affected_urls)} pages")
                lines.append("")
                lines.append("<details><summary>Affected pages</summary>")
                lines.append("")
                for u in finding.affected_urls:
                    lines.append(f"- [{u}]({u})")
                lines.append("")
                lines.append("</details>")
            else:
                lines.append(f"**URL:** [{finding.url}]({finding.url})")
            lines.append("")

        if finding.element_selector:
            lines.append(f"**Element:** `{finding.element_selector}`")
            lines.append("")

        if finding.element_text:
            lines.append(f"**Element Text:** {self._escape_html_tags(finding.element_text)}")
            lines.append("")

        if finding.expected_behavior or finding.actual_behavior:
            lines.append("| Expected | Actual |")
            lines.append("| --- | --- |")
            expected = self._escape_html_tags(finding.expected_behavior or "-").replace("|", "\\|")
            actual = self._escape_html_tags(finding.actual_behavior or "-").replace("|", "\\|")
            lines.append(f"| {expected} | {actual} |")
            lines.append("")

        if finding.evidence:
            lines.append(f"**Evidence:** `{finding.evidence}`")
            lines.append("")

        if finding.recommendation:
            lines.append(f"**Recommendation:** {self._escape_html_tags(finding.recommendation)}")
            lines.append("")

        if finding.steps_to_reproduce:
            lines.append("**Steps to Reproduce:**")
            for step in finding.steps_to_reproduce:
                lines.append(f"1. {step}")
            lines.append("")

        if finding.screenshot_path:
            # Make screenshot path relative to the markdown file location
            from pathlib import Path
            report_dir = Path(self.output_dir)
            screenshot_path = Path(finding.screenshot_path)
            try:
                rel_path = screenshot_path.relative_to(report_dir)
            except ValueError:
                # If not a subpath, fall back to os.path.relpath
                rel_path = Path(os.path.relpath(str(screenshot_path), str(report_dir)))
            lines.append(f"**Screenshot:** ![Screenshot]({rel_path})")
            lines.append("")

        if finding.raw_error:
            lines.append("**Raw Error:**")
            lines.append("")
            lines.append("```")
            lines.append(finding.raw_error[:500])
            lines.append("```")
            lines.append("")

        if finding.metadata:
            import json
            lines.append("<details><summary><strong>Additional Details</strong></summary>")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(finding.metadata, indent=2, default=str))
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        # Strip trailing blank lines — the caller appends exactly one blank
        # between findings, so we avoid producing double blank lines.
        while lines and lines[-1] == "":
            lines.pop()

        return lines

    def _format_cross_browser(self, session: "TestSession") -> list[str]:
        """Format cross-browser compatibility matrix and comparison breakdown."""
        lines = [
            "## 🌐 Cross-Browser Compatibility Matrix",
            "",
            "| Browser | Engine Version | Status | Duration | Findings | Launch / Error Details |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        comparison = session.get_cross_browser_comparison()
        for b, info in comparison["browser_matrix"].items():
            ver = info.get("version") or "N/A"
            status = str(info.get("status", "unknown")).upper()
            dur = f"{info.get('duration_seconds', 0.0):.1f}s"
            findings_count = str(info.get("total_findings", 0))
            err = info.get("error") or "-"
            if err != "-":
                err = f"`{err[:80]}...`" if len(err) > 80 else f"`{err}`"
            lines.append(f"| {b.title()} | {ver} | {status} | {dur} | {findings_count} | {err} |")
        lines.append("")

        common = comparison["common_findings"]
        lines.append(f"### Common Issues Across All Browsers ({len(common)})")
        lines.append("")
        if common:
            lines.append("| Severity | Title | Affected URL |")
            lines.append("| --- | --- | --- |")
            for f in common:
                sev = f.get("severity", "info").upper()
                emoji = self._severity_emoji(f.get("severity", "info"))
                lines.append(f"| {emoji} {sev} | {f.get('title', '')} | {f.get('url', '')} |")
        else:
            lines.append("No common issues observed across all browsers.")
        lines.append("")

        specific = comparison["browser_specific_findings"]
        if specific:
            lines.append("### Browser-Specific Issues")
            lines.append("")
            for b, items in specific.items():
                lines.append(f"#### Issues Unique to {b.title()} ({len(items)})")
                lines.append("")
                lines.append("| Severity | Title | Affected URL |")
                lines.append("| --- | --- | --- |")
                for f in items:
                    sev = f.get("severity", "info").upper()
                    emoji = self._severity_emoji(f.get("severity", "info"))
                    lines.append(f"| {emoji} {sev} | {f.get('title', '')} | {f.get('url', '')} |")
                lines.append("")

        return lines
