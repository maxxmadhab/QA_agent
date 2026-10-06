"""Security & Vulnerability Tester for Bandit and pip-audit."""

import json
import os
import subprocess
import sys

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class SecurityTester(BaseTester):
    """Executes Bandit AST security scanning and pip-audit dependency vulnerability checks."""

    def __init__(self, target_dir: str = ".", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_dir = os.path.abspath(target_dir)

    def run(self) -> list[Finding]:
        """Run all security checks."""
        return self.run_all()

    def run_bandit(self) -> list[Finding]:
        """Run Bandit security scan on Python source files."""
        findings: list[Finding] = []
        cmd = [sys.executable, "-m", "bandit", "-r", self.target_dir, "-f", "json", "-q"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.stdout.strip():
                try:
                    data = json.loads(res.stdout)
                    results = data.get("results", [])
                    for idx, item in enumerate(results, 1):
                        test_id = item.get("test_id", "B000")
                        issue_text = item.get("issue_text", "Security issue detected")
                        issue_sev = item.get("issue_severity", "MEDIUM").upper()
                        filename = item.get("filename", self.target_dir)
                        line = item.get("line_number", 1)
                        file_url = filename.replace("\\", "/")

                        sev = Severity.MEDIUM
                        if issue_sev == "HIGH":
                            sev = Severity.HIGH
                        elif issue_sev == "CRITICAL":
                            sev = Severity.CRITICAL
                        elif issue_sev == "LOW":
                            sev = Severity.LOW

                        findings.append(
                            Finding(
                                test_id=f"BANDIT-{test_id}-{idx:03d}",
                                title=f"Security Risk [{test_id}]: {issue_text}",
                                description=f"Bandit found security risk in {os.path.basename(filename)} line {line}: {issue_text}",
                                category=FindingCategory.SECURITY,
                                severity=sev,
                                url=f"file:///{file_url}#L{line}",
                                tool="bandit",
                                status=FindingStatus.FAILED,
                                evidence={
                                    "filename": filename,
                                    "line": line,
                                    "issue_id": test_id,
                                    "more_info": item.get("more_info"),
                                    "code": item.get("code"),
                                },
                                recommendation="Remediate insecure code pattern according to Bandit documentation.",
                            )
                        )
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            findings.append(
                Finding(
                    test_id="BANDIT-ERR",
                    title="Bandit Security Scan Failure",
                    description=f"Could not execute bandit: {str(e)}",
                    category=FindingCategory.SECURITY,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="bandit",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure bandit is installed.",
                )
            )

        return findings

    def run_pip_audit(self) -> list[Finding]:
        """Run pip-audit to check Python dependencies for known CVEs."""
        findings: list[Finding] = []
        cmd = [sys.executable, "-m", "pip_audit", "-f", "json"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.stdout.strip():
                try:
                    data = json.loads(res.stdout)
                    dependencies = data.get("dependencies", [])
                    idx = 1
                    for dep in dependencies:
                        vulns = dep.get("vulns", [])
                        pkg_name = dep.get("name")
                        pkg_ver = dep.get("version")
                        for v in vulns:
                            cve_id = v.get("id", "VULN")
                            desc = v.get("description", "Vulnerable dependency package")
                            findings.append(
                                Finding(
                                    test_id=f"AUDIT-{cve_id}-{idx:03d}",
                                    title=f"Vulnerable Dependency: {pkg_name} {pkg_ver} ({cve_id})",
                                    description=f"Package {pkg_name} {pkg_ver} has known vulnerability {cve_id}: {desc[:200]}",
                                    category=FindingCategory.DEPENDENCY,
                                    severity=Severity.HIGH,
                                    url=self.target_dir,
                                    tool="pip-audit",
                                    status=FindingStatus.FAILED,
                                    evidence={
                                        "package": pkg_name,
                                        "version": pkg_ver,
                                        "cve_id": cve_id,
                                        "fix_versions": v.get("fix_versions", []),
                                    },
                                    recommendation=f"Upgrade package {pkg_name} to a secure patched version.",
                                )
                            )
                            idx += 1
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            findings.append(
                Finding(
                    test_id="AUDIT-ERR",
                    title="pip-audit Scan Failure",
                    description=f"Could not execute pip-audit: {str(e)}",
                    category=FindingCategory.DEPENDENCY,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="pip-audit",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure pip-audit is installed.",
                )
            )

        return findings

    def run_all(self) -> list[Finding]:
        """Run all security checks."""
        return self.run_bandit() + self.run_pip_audit()
