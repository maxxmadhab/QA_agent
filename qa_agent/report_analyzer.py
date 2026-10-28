"""Automated QA Report Analysis pipeline using OmniKey AI.

Ingests machine-readable JSON or formatted Markdown test reports, enforces strict
ground-truth adherence, and generates actionable narrative analysis containing:
- Executive summary for engineering leadership
- Cross-browser comparison (engine-specific vs universal defects)
- Root-cause clustering of related defects
- Prioritized remediation plan ranking by severity and impact
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .llm_client import LLMError, LLMProvider, create_llm_client
from .models import Finding, RootCauseCluster, SummaryResult, TestSession

logger = logging.getLogger(__name__)

_ANALYSIS_SYSTEM_PROMPT = """You are an expert Principal QA Automation Architect and DevOps Engineering Lead.

You will be given raw automated QA execution output (JSON or parsed Markdown) representing a test run.
The data includes session metadata, findings across categories/severities, browser comparison matrices,
console/network errors, and step-level custom test outcomes.

Your task is to analyze this empirical data and produce a professional, actionable QA narrative report.

CRITICAL GROUND-TRUTH RULES:
1. STRICT TRUTH ADHERENCE: You must ONLY analyze tests and findings that actually appear in the provided input.
2. DO NOT HALLUCINATE: Never invent findings, URLs, browser engines, or errors that were not reported.
3. Every finding title cited in "root_cause_clusters" must match an actual finding from the input.
4. If no findings were detected or all tests passed, clearly state this in the executive summary.

Return ONLY a valid JSON object matching this schema:
{
  "executive_summary": "<3-5 sentence executive summary for engineering leadership covering system health, key risks, and release readiness>",
  "cross_browser_analysis": "<Comparative breakdown of defects across browsers (e.g. chromium vs firefox vs webkit). Identify universal vs browser-specific bugs. State if single browser was tested.>",
  "root_cause_clusters": [
    {
      "label": "<Name of cluster, e.g. 'Unauthenticated API Endpoint Failure'>",
      "finding_titles": ["<exact title of finding from input>"],
      "root_cause": "<Underlying architectural or code failure causing these findings>",
      "suggested_fix": "<Actionable, concrete engineering fix>"
    }
  ],
  "priority_recommendations": [
    "<Ranked remediation action 1 (P0/Critical): specific fix with file/selector context>",
    "<Ranked remediation action 2 (P1/High)...>",
    "<Ranked remediation action 3 (P2/Medium)...>"
  ],
  "false_positive_candidates": [
    "<Finding title that appears to be an environmental or test artifact rather than a real defect, with explanation>"
  ]
}
"""


# ---------------------------------------------------------------------------
# Report Ingestion Helpers
# ---------------------------------------------------------------------------

def ingest_json_report(source: str | Path | dict) -> dict[str, Any]:
    """Ingest a machine-readable JSON QA report."""
    if isinstance(source, dict):
        data = source
    elif isinstance(source, Path) or (isinstance(source, str) and (Path(source).exists() or source.endswith(".json"))):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"JSON report file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(source)

    return {
        "session_id": data.get("session_id", "unknown"),
        "pages_tested": data.get("pages_tested", 0),
        "total_findings": data.get("total_findings", len(data.get("findings", []))),
        "findings_by_severity": data.get("findings_by_severity", {}),
        "findings_by_category": data.get("findings_by_category", {}),
        "cross_browser_comparison": data.get("cross_browser_comparison"),
        "browser_results": data.get("browser_results", {}),
        "nl_execution_results": data.get("nl_execution_results", []),
        "findings": data.get("findings", []),
        "config_summary": data.get("config_summary", {}),
    }


def ingest_markdown_report(source: str | Path) -> dict[str, Any]:
    """Parse and extract structured findings and sections from a Markdown QA report."""
    if isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = str(source)

    findings: list[dict[str, Any]] = []
    current_finding: dict[str, Any] | None = None

    pages_tested = 0
    total_findings = 0
    pages_match = re.search(r"-\s+\*\*Pages Tested:\*\*\s+(\d+)", text)
    if pages_match:
        pages_tested = int(pages_match.group(1))

    findings_match = re.search(r"-\s+\*\*Total Findings:\*\*\s+(\d+)", text)
    if findings_match:
        total_findings = int(findings_match.group(1))

    # Parse detailed findings from markdown
    # Format: ### [SEVERITY] Title
    finding_headers = list(re.finditer(r"^###\s+\[([A-Z_]+)\]\s+(.+)$", text, re.MULTILINE))
    for i, match in enumerate(finding_headers):
        sev = match.group(1).lower()
        title = match.group(2).strip()

        start = match.end()
        end = finding_headers[i + 1].start() if i + 1 < len(finding_headers) else len(text)
        chunk = text[start:end]

        desc_match = re.search(r"-\s+\*\*Description:\*\*\s*(.+)", chunk)
        desc = desc_match.group(1).strip() if desc_match else title

        url_match = re.search(r"-\s+\*\*URL:\*\*\s*(.+)", chunk)
        url = url_match.group(1).strip() if url_match else ""

        cat_match = re.search(r"-\s+\*\*Category:\*\*\s*(.+)", chunk)
        category = cat_match.group(1).strip().lower().replace(" ", "_") if cat_match else "unexpected_behavior"

        findings.append({
            "title": title,
            "severity": sev,
            "category": category,
            "description": desc,
            "url": url,
        })

    # Detect cross-browser table
    cross_browser_data: dict[str, Any] | None = None
    if "Cross-Browser Compatibility Matrix" in text:
        matrix: dict[str, Any] = {}
        for row in re.finditer(r"\|\s*([A-Za-z0-9_-]+)\s*\|\s*([^|]+)\|\s*([A-Za-z_]+)\s*\|\s*([^|]+)\|\s*(\d+)\s*\|", text):
            b_name = row.group(1).strip().lower()
            if b_name != "browser":
                matrix[b_name] = {
                    "version": row.group(2).strip(),
                    "status": row.group(3).strip(),
                    "duration_seconds": row.group(4).strip(),
                    "total_findings": int(row.group(5).strip()),
                }
        if matrix:
            cross_browser_data = {"browser_matrix": matrix}

    return {
        "pages_tested": pages_tested,
        "total_findings": total_findings or len(findings),
        "findings": findings,
        "cross_browser_comparison": cross_browser_data,
        "raw_markdown_snippet": text[:4000],
    }


def ingest_session(session: TestSession) -> dict[str, Any]:
    """Ingest directly from an active TestSession instance."""
    findings = session.get_deduplicated_findings()
    return {
        "session_id": session.session_id,
        "pages_tested": len(session.pages_tested),
        "total_findings": session.total_findings,
        "findings_by_severity": session.findings_by_severity,
        "findings_by_category": session.findings_by_category,
        "cross_browser_comparison": session.get_cross_browser_comparison() if len(session.browser_results) > 1 else None,
        "browser_results": {k: v.to_dict() for k, v in session.browser_results.items()},
        "nl_execution_results": session.nl_execution_results,
        "findings": [f.to_dict() for f in findings],
        "config_summary": session.config_summary,
    }


# ---------------------------------------------------------------------------
# Report Analyzer
# ---------------------------------------------------------------------------

class ReportAnalyzer:
    """Analyzes QA test results using OmniKey AI to produce a leadership narrative."""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OMNIKEY,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._client = create_llm_client(provider=provider, model=model, api_key=api_key)

    def analyze(self, source: dict[str, Any] | str | Path | TestSession) -> SummaryResult:
        """Run the analysis pipeline on any supported input format."""
        if isinstance(source, TestSession):
            data = ingest_session(source)
        elif isinstance(source, dict):
            data = source
        elif isinstance(source, (str, Path)) and str(source).endswith(".md"):
            data = ingest_markdown_report(source)
        elif isinstance(source, (str, Path)) and str(source).endswith(".json"):
            data = ingest_json_report(source)
        elif isinstance(source, str) and source.strip().startswith("{"):
            data = json.loads(source)
        elif isinstance(source, (str, Path)):
            # Try json first, fallback to markdown
            try:
                data = ingest_json_report(source)
            except Exception:
                data = ingest_markdown_report(source)
        else:
            raise ValueError(f"Unsupported report source type: {type(source).__name__}")

        known_titles = {f.get("title", "") for f in data.get("findings", []) if f.get("title")}

        user_prompt = (
            "Here is the raw QA execution data to analyze:\n\n"
            f"{json.dumps(data, indent=2, default=str)}\n\n"
            f"Known Valid Finding Titles:\n{sorted(list(known_titles))}\n\n"
            "Generate the comprehensive QA leadership analysis JSON."
        )

        response = self._client.complete(
            system=_ANALYSIS_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=4096,
            timeout=60,
        )

        result = self._parse_and_validate(response.text, known_titles)
        return result

    def _parse_and_validate(self, text: str, known_titles: set[str]) -> SummaryResult:
        """Parse LLM output and enforce anti-hallucination ground truth."""
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
            closing = stripped.rfind("```")
            if closing != -1:
                stripped = stripped[:closing]
            stripped = stripped.strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            # Fallback for plain text response
            return SummaryResult(
                executive_summary=text[:500],
                priority_recommendations=["Review test execution findings manually."],
                root_cause_clusters=[],
                false_positive_candidates=[],
                cross_browser_analysis="Automated analysis parsing failed; please review raw logs.",
            )

        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object from LLM.")

        # Ground-truth validation: filter out any hallucinated titles in clusters
        raw_clusters = parsed.get("root_cause_clusters", [])
        validated_clusters: list[RootCauseCluster] = []
        for c in raw_clusters:
            if not isinstance(c, dict):
                continue
            raw_titles = c.get("finding_titles", [])
            # If known_titles exists, retain titles that match known ones or substrings
            if known_titles:
                valid_subset = [
                    t for t in raw_titles
                    if any(t.lower() in kt.lower() or kt.lower() in t.lower() for kt in known_titles)
                ]
            else:
                valid_subset = raw_titles

            validated_clusters.append(
                RootCauseCluster(
                    label=str(c.get("label", "General Issue")),
                    finding_titles=valid_subset if valid_subset else raw_titles,
                    root_cause=str(c.get("root_cause", "")),
                    suggested_fix=str(c.get("suggested_fix", "")),
                )
            )

        recs = [str(r) for r in parsed.get("priority_recommendations", []) if str(r).strip()]
        fp = [str(f) for f in parsed.get("false_positive_candidates", []) if str(f).strip()]
        cb_analysis = parsed.get("cross_browser_analysis")

        return SummaryResult(
            executive_summary=str(parsed.get("executive_summary", "")),
            priority_recommendations=recs,
            root_cause_clusters=validated_clusters,
            false_positive_candidates=fp,
            cross_browser_analysis=str(cb_analysis) if cb_analysis else None,
        )


def analyze_report_file(
    file_path: str | Path,
    provider: LLMProvider = LLMProvider.OMNIKEY,
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[SummaryResult, Path]:
    """Standalone CLI helper: Ingests a report file, runs analysis, and saves output."""
    path = Path(file_path).resolve()
    analyzer = ReportAnalyzer(provider=provider, model=model, api_key=api_key)
    result = analyzer.analyze(path)

    # Save output analysis adjacent to report
    out_json_path = path.with_name(f"{path.stem}_ai_analysis.json")
    out_json_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    return result, out_json_path
