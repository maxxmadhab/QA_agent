"""Postman / Newman Collection Tester."""

import json
import os
import shutil
import subprocess
import tempfile

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class NewmanTester(BaseTester):
    """Executes Postman collections via Newman CLI."""

    def __init__(self, collection_path: str, environment_path: str | None = None, page=None, config=None):
        super().__init__(page=page, config=config)
        self.collection_path = collection_path
        self.environment_path = environment_path

    @staticmethod
    def is_newman_installed() -> bool:
        """Check if newman executable is available on PATH."""
        return shutil.which("newman") is not None

    def run(self) -> list[Finding]:
        """Run Postman collection and parse results into unified findings."""
        findings: list[Finding] = []

        if not self.is_newman_installed():
            findings.append(
                Finding(
                    test_id="NEWMAN-000",
                    title="Newman Executable Not Found",
                    description="Postman CLI runner 'newman' is not installed or not available on PATH.",
                    category=FindingCategory.API,
                    severity=Severity.HIGH,
                    url=self.collection_path,
                    tool="newman",
                    status=FindingStatus.FAILED,
                    evidence={"collection": self.collection_path},
                    recommendation="Install Newman using 'npm install -g newman' to run Postman collections.",
                )
            )
            return findings

        if not os.path.exists(self.collection_path):
            findings.append(
                Finding(
                    test_id="NEWMAN-001",
                    title="Postman Collection File Missing",
                    description=f"Collection file not found at: {self.collection_path}",
                    category=FindingCategory.API,
                    severity=Severity.HIGH,
                    url=self.collection_path,
                    tool="newman",
                    status=FindingStatus.FAILED,
                    evidence={"collection_path": self.collection_path},
                    recommendation="Provide a valid path to a Postman collection JSON file.",
                )
            )
            return findings

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            report_path = tmp.name

        try:
            cmd = ["newman", "run", self.collection_path, "--reporters", "json", "--reporter-json-export", report_path]
            if self.environment_path and os.path.exists(self.environment_path):
                cmd.extend(["-e", self.environment_path])

            subprocess.run(cmd, capture_output=True, text=True, check=False)

            if os.path.exists(report_path) and os.path.getsize(report_path) > 0:
                with open(report_path, encoding="utf-8") as f:
                    data = json.load(f)

                failures = data.get("run", {}).get("failures", [])
                for idx, fail in enumerate(failures, 1):
                    source = fail.get("source", {})
                    name = source.get("name", "Unnamed Request")
                    error = fail.get("error", {})
                    findings.append(
                        Finding(
                            test_id=f"NEWMAN-FAIL-{idx:03d}",
                            title=f"Postman Assertion Failed: {name}",
                            description=error.get("message", "Postman assertion failure"),
                            category=FindingCategory.API,
                            severity=Severity.HIGH,
                            url=self.collection_path,
                            tool="newman",
                            status=FindingStatus.FAILED,
                            evidence={
                                "request_name": name,
                                "test_name": error.get("name"),
                                "test_message": error.get("message"),
                            },
                            recommendation="Inspect Postman assertion failure and fix corresponding API logic.",
                        )
                    )
        except Exception as e:
            findings.append(
                Finding(
                    test_id="NEWMAN-EXEC-ERR",
                    title="Newman Execution Exception",
                    description=f"Error executing Newman runner: {str(e)}",
                    category=FindingCategory.API,
                    severity=Severity.HIGH,
                    url=self.collection_path,
                    tool="newman",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure Newman is properly installed and collection format is valid.",
                )
            )
        finally:
            if os.path.exists(report_path):
                try:
                    os.remove(report_path)
                except OSError:
                    pass

        return findings
