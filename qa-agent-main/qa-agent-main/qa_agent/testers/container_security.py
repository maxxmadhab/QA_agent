"""Container Security Vulnerability Scanner using Trivy."""

import json
import os
import shutil
import subprocess

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class ContainerSecurityTester(BaseTester):
    """Scans container images and filesystem for vulnerabilities using Trivy."""

    def __init__(self, target_image: str | None = None, target_dir: str = ".", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_image = target_image
        self.target_dir = os.path.abspath(target_dir)

    def run(self) -> list[Finding]:
        """Run Trivy vulnerability scan."""
        return self.run_trivy_scan()

    def run_trivy_scan(self) -> list[Finding]:
        """Execute Trivy vulnerability scan."""
        findings: list[Finding] = []

        if not shutil.which("trivy"):
            findings.append(
                Finding(
                    test_id="TRIVY-000",
                    title="Trivy Container Scanner Not Installed",
                    description="Trivy security scanner binary was not found on PATH.",
                    category=FindingCategory.CONTAINER,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="trivy",
                    status=FindingStatus.SKIPPED,
                    evidence={"target_dir": self.target_dir},
                    recommendation="Install Trivy (https://github.com/aquasecurity/trivy) for container vulnerability scanning.",
                )
            )
            return findings

        cmd = ["trivy", "fs", "--format", "json", self.target_dir] if not self.target_image else ["trivy", "image", "--format", "json", self.target_image]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.stdout.strip():
                try:
                    data = json.loads(res.stdout)
                    results = data.get("Results", [])
                    idx = 1
                    for r in results:
                        target = r.get("Target", "Container")
                        vulns = r.get("Vulnerabilities", []) or []
                        for v in vulns:
                            cve_id = v.get("VulnerabilityID", "CVE-UNKNOWN")
                            pkg_name = v.get("PkgName", "UnknownPkg")
                            installed_ver = v.get("InstalledVersion", "0.0")
                            fixed_ver = v.get("FixedVersion", "N/A")
                            title = v.get("Title", f"Vulnerability in {pkg_name}")
                            sev_str = v.get("Severity", "MEDIUM").upper()

                            sev = Severity.MEDIUM
                            if sev_str == "CRITICAL":
                                sev = Severity.CRITICAL
                            elif sev_str == "HIGH":
                                sev = Severity.HIGH
                            elif sev_str == "LOW":
                                sev = Severity.LOW

                            td_url = self.target_dir.replace("\\", "/")
                            findings.append(
                                Finding(
                                    test_id=f"TRIVY-{cve_id}-{idx:03d}",
                                    title=f"Container Vulnerability [{cve_id}]: {pkg_name} {installed_ver}",
                                    description=f"{title} (Package: {pkg_name} {installed_ver}, Fix: {fixed_ver}) in {target}",
                                    category=FindingCategory.CONTAINER,
                                    severity=sev,
                                    url=f"file:///{td_url}",
                                    tool="trivy",
                                    status=FindingStatus.FAILED,
                                    evidence={
                                        "cve": cve_id,
                                        "package": pkg_name,
                                        "installed_version": installed_ver,
                                        "fixed_version": fixed_ver,
                                        "target": target,
                                    },
                                    recommendation=f"Update {pkg_name} to version {fixed_ver} or rebuild base container image.",
                                )
                            )
                            idx += 1
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            findings.append(
                Finding(
                    test_id="TRIVY-ERR",
                    title="Trivy Scan Execution Error",
                    description=f"Error executing Trivy scan: {str(e)}",
                    category=FindingCategory.CONTAINER,
                    severity=Severity.LOW,
                    url=self.target_dir,
                    tool="trivy",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Ensure Trivy is functioning properly.",
                )
            )

        return findings
