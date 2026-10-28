"""Docker and Container Health Tester."""

import os
import re
import shutil
import subprocess

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class DockerTester(BaseTester):
    """Tester for Dockerfile static checks (Hadolint), compose configuration, and container health."""

    def __init__(self, target_dir: str = ".", dockerfile_path: str = "Dockerfile", compose_path: str = "docker-compose.yml", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_dir = os.path.abspath(target_dir)
        self.dockerfile_path = os.path.join(self.target_dir, dockerfile_path) if not os.path.isabs(dockerfile_path) else dockerfile_path
        self.compose_path = os.path.join(self.target_dir, compose_path) if not os.path.isabs(compose_path) else compose_path

    def run(self) -> list[Finding]:
        """Run all Docker & container checks."""
        return self.run_all()

    def check_dockerfile_hadolint(self) -> list[Finding]:
        """Run Hadolint CLI on Dockerfile if installed, or fallback AST checks."""
        findings: list[Finding] = []
        df_url = self.dockerfile_path.replace("\\", "/")

        if not os.path.exists(self.dockerfile_path):
            findings.append(
                Finding(
                    test_id="DOCKER-001",
                    title="Missing Dockerfile",
                    description=f"Dockerfile not found at {self.dockerfile_path}",
                    category=FindingCategory.CONTAINER,
                    severity=Severity.MEDIUM,
                    url=f"file:///{df_url}",
                    tool="docker-tester",
                    status=FindingStatus.WARNING,
                    evidence={"path": self.dockerfile_path},
                    recommendation="Add a Dockerfile for containerization.",
                )
            )
            return findings

        # Try Hadolint CLI first
        if shutil.which("hadolint"):
            try:
                cmd = ["hadolint", "--format", "json", self.dockerfile_path]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.stdout.strip():
                    import json
                    diagnostics = json.loads(res.stdout)
                    for idx, diag in enumerate(diagnostics, 1):
                        code = diag.get("code", "DL3000")
                        message = diag.get("message", "Hadolint lint issue")
                        line = diag.get("line", 1)
                        sev_str = diag.get("level", "warning").lower()
                        sev = Severity.HIGH if sev_str in ("error", "critical") else Severity.MEDIUM

                        findings.append(
                            Finding(
                                test_id=f"HADOLINT-{code}-{idx:03d}",
                                title=f"Hadolint [{code}]: {message}",
                                description=f"Dockerfile line {line}: {message}",
                                category=FindingCategory.CONTAINER,
                                severity=sev,
                                url=f"file:///{df_url}#L{line}",
                                tool="hadolint",
                                status=FindingStatus.FAILED,
                                evidence={"line": line, "code": code, "level": sev_str},
                                recommendation=f"Follow Dockerfile best practice rule {code}.",
                            )
                        )
                    return findings
            except Exception:
                pass

        # Fallback built-in static Dockerfile checks
        try:
            with open(self.dockerfile_path, encoding="utf-8") as f:
                lines = f.readlines()

            content = "".join(lines)
            if "USER " not in content:
                findings.append(
                    Finding(
                        test_id="DOCKER-SEC-001",
                        title="Dockerfile Runs as Root User",
                        description="Dockerfile does not specify a non-root USER instruction.",
                        category=FindingCategory.CONTAINER,
                        severity=Severity.MEDIUM,
                        url=f"file:///{df_url}",
                        tool="docker-tester",
                        status=FindingStatus.WARNING,
                        evidence={"file": self.dockerfile_path},
                        recommendation="Specify a non-root USER in Dockerfile for better container security.",
                    )
                )

            if "HEALTHCHECK" not in content:
                findings.append(
                    Finding(
                        test_id="DOCKER-HEALTH-001",
                        title="Missing Docker HEALTHCHECK Instruction",
                        description="Dockerfile does not define a HEALTHCHECK instruction.",
                        category=FindingCategory.CONTAINER,
                        severity=Severity.LOW,
                        url=f"file:///{df_url}",
                        tool="docker-tester",
                        status=FindingStatus.WARNING,
                        evidence={"file": self.dockerfile_path},
                        recommendation="Add a HEALTHCHECK instruction to allow orchestration health monitoring.",
                    )
                )

            if re.search(r"apt-get install(?!.*rm -rf /var/lib/apt/lists)", content, re.DOTALL):
                findings.append(
                    Finding(
                        test_id="DOCKER-OPT-001",
                        title="Inefficient apt-get Layer Cleanup",
                        description="apt-get install without cleaning /var/lib/apt/lists/* increases image size.",
                        category=FindingCategory.CONTAINER,
                        severity=Severity.LOW,
                        url=f"file:///{df_url}",
                        tool="docker-tester",
                        status=FindingStatus.WARNING,
                        evidence={"file": self.dockerfile_path},
                        recommendation="Clean up apt cache with 'rm -rf /var/lib/apt/lists/*' after apt-get install.",
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    test_id="DOCKER-READ-ERR",
                    title="Error Reading Dockerfile",
                    description=f"Could not read Dockerfile: {str(e)}",
                    category=FindingCategory.CONTAINER,
                    severity=Severity.LOW,
                    url=f"file:///{df_url}",
                    tool="docker-tester",
                    status=FindingStatus.WARNING,
                    evidence={"error": str(e)},
                    recommendation="Verify Dockerfile path and read permissions.",
                )
            )

        return findings

    def check_docker_compose(self) -> list[Finding]:
        """Audit docker-compose.yml configuration for security & best practices."""
        findings: list[Finding] = []
        dc_url = self.compose_path.replace("\\", "/")

        if not os.path.exists(self.compose_path):
            return findings

        try:
            with open(self.compose_path, encoding="utf-8") as f:
                content = f.read()

            if "privileged: true" in content:
                findings.append(
                    Finding(
                        test_id="COMPOSE-SEC-001",
                        title="Excessive Container Privileges in Docker Compose",
                        description="One or more services specify 'privileged: true', granting root-level host access.",
                        category=FindingCategory.INFRASTRUCTURE,
                        severity=Severity.HIGH,
                        url=f"file:///{dc_url}",
                        tool="docker-tester",
                        status=FindingStatus.FAILED,
                        evidence={"file": self.compose_path},
                        recommendation="Avoid 'privileged: true' unless strictly necessary.",
                    )
                )

            if re.search(r"(?:password|secret|key)[:=]\s*['\"][^'\"]+['\"]", content, re.IGNORECASE):
                findings.append(
                    Finding(
                        test_id="COMPOSE-SEC-002",
                        title="Hardcoded Secret in Docker Compose",
                        description="Hardcoded password or secret string detected in docker-compose.yml.",
                        category=FindingCategory.SECURITY,
                        severity=Severity.HIGH,
                        url=f"file:///{dc_url}",
                        tool="docker-tester",
                        status=FindingStatus.FAILED,
                        evidence={"file": self.compose_path},
                        recommendation="Use environment variables or docker secrets instead of hardcoding passwords.",
                    )
                )
        except Exception as e:
            findings.append(
                Finding(
                    test_id="COMPOSE-READ-ERR",
                    title="Error Reading docker-compose.yml",
                    description=f"Could not read compose file: {str(e)}",
                    category=FindingCategory.INFRASTRUCTURE,
                    severity=Severity.LOW,
                    url=f"file:///{dc_url}",
                    tool="docker-tester",
                    status=FindingStatus.WARNING,
                    evidence={"error": str(e)},
                    recommendation="Verify docker-compose.yml syntax.",
                )
            )

        return findings

    def run_all(self) -> list[Finding]:
        """Run Dockerfile & compose auditing."""
        return self.check_dockerfile_hadolint() + self.check_docker_compose()
