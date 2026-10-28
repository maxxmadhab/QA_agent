"""Project Health and Environment Readiness Tester."""

import ast
import importlib
import os

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class ProjectHealthTester(BaseTester):
    """Tester for verifying repository health, configuration, dependencies, and imports."""

    def __init__(self, target_dir: str = ".", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_dir = os.path.abspath(target_dir)

    def run(self) -> list[Finding]:
        """Run all project health checks."""
        return self.run_all()

    def check_python_syntax(self) -> list[Finding]:
        """Check all Python files for syntax errors."""
        findings: list[Finding] = []
        for root, _, files in os.walk(self.target_dir):
            if ".venv" in root or "__pycache__" in root or ".git" in root:
                continue
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    file_url = full_path.replace("\\", "/")
                    try:
                        with open(full_path, encoding="utf-8") as f:
                            ast.parse(f.read(), filename=full_path)
                    except SyntaxError as se:
                        line_no = se.lineno or 1
                        findings.append(
                            Finding(
                                test_id="HEALTH-SYNTAX-001",
                                title=f"Syntax Error in {file}",
                                description=f"Syntax error at line {se.lineno}: {se.msg}",
                                category=FindingCategory.FUNCTIONAL,
                                severity=Severity.CRITICAL,
                                url=f"file:///{file_url}#L{line_no}",
                                tool="project-health",
                                status=FindingStatus.FAILED,
                                evidence={"file": full_path, "line": se.lineno, "msg": se.msg},
                                recommendation="Fix syntax error before executing python code.",
                            )
                        )
                    except Exception as e:
                        findings.append(
                            Finding(
                                test_id="HEALTH-READ-001",
                                title=f"File Read Error in {file}",
                                description=f"Could not read python file: {str(e)}",
                                category=FindingCategory.FUNCTIONAL,
                                severity=Severity.LOW,
                                url=f"file:///{file_url}",
                                tool="project-health",
                                status=FindingStatus.WARNING,
                                evidence={"file": full_path, "error": str(e)},
                                recommendation="Check file permissions and encoding.",
                            )
                        )
        return findings

    def check_required_imports(self, modules: list[str]) -> list[Finding]:
        """Check if critical third-party Python modules can be imported."""
        findings: list[Finding] = []
        for mod in modules:
            try:
                importlib.import_module(mod)
            except ImportError as ie:
                findings.append(
                    Finding(
                        test_id=f"HEALTH-IMPORT-{mod.upper()}",
                        title=f"Missing Critical Dependency: {mod}",
                        description=f"Failed to import required python module '{mod}': {str(ie)}",
                        category=FindingCategory.DEPENDENCY,
                        severity=Severity.HIGH,
                        url=self.target_dir,
                        tool="project-health",
                        status=FindingStatus.FAILED,
                        evidence={"module": mod, "error": str(ie)},
                        recommendation=f"Install missing module using 'pip install {mod}'.",
                    )
                )
        return findings

    def check_config_files(self, required_files: list[str]) -> list[Finding]:
        """Check for presence of key configuration files."""
        findings: list[Finding] = []
        for req in required_files:
            target_file = os.path.join(self.target_dir, req)
            if not os.path.exists(target_file):
                findings.append(
                    Finding(
                        test_id=f"HEALTH-CONFIG-{os.path.basename(req).upper()}",
                        title=f"Missing Configuration File: {req}",
                        description=f"Expected configuration file '{req}' was not found in repository.",
                        category=FindingCategory.FUNCTIONAL,
                        severity=Severity.MEDIUM,
                        url=self.target_dir,
                        tool="project-health",
                        status=FindingStatus.WARNING,
                        evidence={"missing_file": req},
                        recommendation=f"Create or restore missing '{req}' configuration file.",
                    )
                )
        return findings

    def run_all(self, critical_modules: list[str] | None = None, required_configs: list[str] | None = None) -> list[Finding]:
        """Run all project health checks."""
        modules = critical_modules or ["playwright", "httpx"]
        configs = required_configs or ["pyproject.toml"]
        return self.check_python_syntax() + self.check_required_imports(modules) + self.check_config_files(configs)
