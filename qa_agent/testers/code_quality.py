"""Code Quality Tester for Ruff and mypy linting/type checking."""

import json
import os
import subprocess
import sys

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class CodeQualityTester(BaseTester):
    """Executes Ruff static analysis and mypy type checks."""

    def __init__(self, target_dir: str = ".", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_dir = os.path.abspath(target_dir)

    def run(self) -> list[Finding]:
        """Run all code quality checks."""
        return self.run_all()

    def run_ruff(self) -> list[Finding]:
        """Run Ruff linter and return findings."""
        findings: list[Finding] = []
        cmd = [sys.executable, "-m", "ruff", "check", self.target_dir, "--output-format", "json"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.stdout.strip():
                try:
                    diagnostics = json.loads(res.stdout)
                    for idx, diag in enumerate(diagnostics, 1):
                        code = diag.get("code", "RUFF")
                        filename = diag.get("filename", self.target_dir)
                        location = diag.get("location", {})
                        line = location.get("row", 1)
                        file_url = filename.replace("\\", "/")
                        findings.append(
                            Finding(
                                test_id=f"RUFF-{code}-{idx:03d}",
                                title=f"Ruff Lint Issue [{code}]: {diag.get('message')}",
                                description=f"Code quality issue in {os.path.basename(filename)} at line {line}: {diag.get('message')}",
                                category=FindingCategory.CODE_QUALITY,
                                severity=Severity.LOW if code.startswith("W") else Severity.MEDIUM,
                                url=f"file:///{file_url}#L{line}",
                                tool="ruff",
                                status=FindingStatus.FAILED,
                                evidence={
                                    "file": filename,
                                    "line": line,
                                    "rule_code": code,
                                    "message": diag.get("message"),
                                },
                                recommendation=f"Fix lint issue according to Ruff rule {code}.",
                            )
                        )
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            findings.append(
                Finding(
                    test_id="RUFF-ERR",
                    title="Ruff Linter Execution Failure",
                    description=f"Could not execute ruff: {str(e)}",
                    category=FindingCategory.CODE_QUALITY,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="ruff",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure ruff is installed.",
                )
            )

        return findings

    def run_mypy(self) -> list[Finding]:
        """Run mypy type checker and return findings."""
        findings: list[Finding] = []
        cmd = [sys.executable, "-m", "mypy", self.target_dir, "--hide-error-context", "--no-color-output"]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            for idx, line in enumerate(res.stdout.splitlines(), 1):
                if ": error:" in line or ": warning:" in line:
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        file_path, line_no, level, msg = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                        file_url = file_path.replace("\\", "/")
                        findings.append(
                            Finding(
                                test_id=f"MYPY-{idx:03d}",
                                title=f"mypy {level.capitalize()}: {msg}",
                                description=f"Type error in {file_path} at line {line_no}: {msg}",
                                category=FindingCategory.CODE_QUALITY,
                                severity=Severity.MEDIUM if level == "error" else Severity.LOW,
                                url=f"file:///{file_url}#L{line_no}",
                                tool="mypy",
                                status=FindingStatus.FAILED,
                                evidence={"file": file_path, "line": line_no, "level": level, "message": msg},
                                recommendation="Update Python type annotations or resolve type mismatch.",
                            )
                        )
        except Exception as e:
            findings.append(
                Finding(
                    test_id="MYPY-ERR",
                    title="mypy Execution Failure",
                    description=f"Could not execute mypy: {str(e)}",
                    category=FindingCategory.CODE_QUALITY,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="mypy",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure mypy is installed.",
                )
            )

        return findings

    def run_all(self) -> list[Finding]:
        """Run all code quality checks."""
        return self.run_ruff() + self.run_mypy()
