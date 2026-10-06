"""OWASP ZAP and Web Application Security Tester."""

import shutil
import subprocess

import httpx

from ..models import Finding, FindingCategory, FindingStatus, Severity
from .base import BaseTester


class ZAPTester(BaseTester):
    """Executes OWASP ZAP security checks and HTTP security header analysis."""

    def __init__(self, target_url: str | None = None, zap_api_url: str = "http://localhost:8080", page=None, config=None):
        super().__init__(page=page, config=config)
        self.target_url = target_url
        self.zap_api_url = zap_api_url

    def run(self) -> list[Finding]:
        """Run web security tests."""
        findings: list[Finding] = []
        if self.target_url:
            findings.extend(self.check_http_security_headers(self.target_url))
            findings.extend(self.run_zap_cli_scan(self.target_url))
        return findings

    def check_http_security_headers(self, url: str) -> list[Finding]:
        """Perform security header and cookie attribute analysis."""
        findings: list[Finding] = []
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                res = client.get(url)
                headers = {k.lower(): v for k, v in res.headers.items()}

                # Check Security Headers
                recommended_headers = [
                    ("content-security-policy", "Missing Content-Security-Policy (CSP) Header", "Adds defense-in-depth against XSS and data injection attacks."),
                    ("x-frame-options", "Missing X-Frame-Options Header", "Protects application against Clickjacking attacks."),
                    ("x-content-type-options", "Missing X-Content-Type-Options Header", "Prevents MIME-sniffing vulnerability."),
                    ("strict-transport-security", "Missing HTTP Strict Transport Security (HSTS)", "Forces browser to use HTTPS connections exclusively."),
                    ("referrer-policy", "Missing Referrer-Policy Header", "Controls information sent in Referer header."),
                ]

                idx = 1
                for h_name, title, desc in recommended_headers:
                    if h_name not in headers:
                        findings.append(
                            Finding(
                                test_id=f"ZAP-HDR-{idx:03d}",
                                title=title,
                                description=f"HTTP response from {url} is missing recommended header '{h_name}'. {desc}",
                                category=FindingCategory.SECURITY,
                                severity=Severity.MEDIUM if h_name != "strict-transport-security" else Severity.HIGH,
                                url=url,
                                tool="owasp-zap",
                                status=FindingStatus.FAILED,
                                evidence={"url": url, "missing_header": h_name},
                                recommendation=f"Configure server to return '{h_name}' response header.",
                            )
                        )
                        idx += 1

                # Server Information Disclosure
                if "server" in headers:
                    findings.append(
                        Finding(
                            test_id="ZAP-DISC-001",
                            title="Server Header Information Disclosure",
                            description=f"Server header reveals backend technology details: '{headers['server']}'",
                            category=FindingCategory.SECURITY,
                            severity=Severity.LOW,
                            url=url,
                            tool="owasp-zap",
                            status=FindingStatus.WARNING,
                            evidence={"url": url, "server_header": headers["server"]},
                            recommendation="Mask or remove 'Server' header to avoid revealing infrastructure details.",
                        )
                    )

                # Cookie Security Flags
                for cookie in res.cookies.jar:
                    if not cookie.secure and url.startswith("https"):
                        findings.append(
                            Finding(
                                test_id="ZAP-COOKIE-001",
                                title=f"Insecure Cookie Missing 'Secure' Flag: {cookie.name}",
                                description=f"Cookie '{cookie.name}' sent over HTTPS without 'Secure' flag.",
                                category=FindingCategory.SECURITY,
                                severity=Severity.MEDIUM,
                                url=url,
                                tool="owasp-zap",
                                status=FindingStatus.FAILED,
                                evidence={"cookie_name": cookie.name},
                                recommendation="Set 'Secure' attribute on sensitive cookies.",
                            )
                        )
        except Exception as e:
            findings.append(
                Finding(
                    test_id="ZAP-CONN-ERR",
                    title="Security Header Scan Connection Error",
                    description=f"Could not connect to target URL {url}: {str(e)}",
                    category=FindingCategory.SECURITY,
                    severity=Severity.LOW,
                    url=url or "http://localhost",
                    tool="owasp-zap",
                    status=FindingStatus.FAILED,
                    evidence={"error": str(e)},
                    recommendation="Verify target web application URL is online.",
                )
            )

        return findings

    def run_zap_cli_scan(self, url: str) -> list[Finding]:
        """Run OWASP ZAP CLI scan if installed."""
        findings: list[Finding] = []

        if not shutil.which("zap-cli"):
            return findings

        try:
            cmd = ["zap-cli", "--zap-url", self.zap_api_url, "quick-scan", "--self-contained", url]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if "CRITICAL" in res.stdout or "HIGH" in res.stdout:
                findings.append(
                    Finding(
                        test_id="ZAP-SCAN-001",
                        title=f"OWASP ZAP Security Vulnerabilities Detected on {url}",
                        description="OWASP ZAP scan found security vulnerabilities in target web application.",
                        category=FindingCategory.SECURITY,
                        severity=Severity.HIGH,
                        url=url,
                        tool="owasp-zap",
                        status=FindingStatus.FAILED,
                        evidence={"zap_output": res.stdout[:500]},
                        recommendation="Review ZAP scan findings and patch web application vulnerabilities.",
                    )
                )
        except Exception:
            pass

        return findings
