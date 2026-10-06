from unittest.mock import MagicMock, patch

from qa_agent.models import Finding, FindingCategory, FindingStatus, Severity, TestSession
from qa_agent.testers.api_tester import APITester
from qa_agent.testers.code_quality import CodeQualityTester
from qa_agent.testers.newman_tester import NewmanTester
from qa_agent.testers.project_health import ProjectHealthTester
from qa_agent.testers.security_checks import SecurityTester


def test_unified_finding_model():
    """Test unified finding structure and serialization."""
    f = Finding(
        test_id="API-001",
        title="Status code mismatch",
        description="Expected 200 got 500",
        category=FindingCategory.API,
        severity=Severity.HIGH,
        url="http://localhost/api/health",
        tool="httpx",
        status=FindingStatus.FAILED,
        evidence={"expected": 200, "actual": 500},
        recommendation="Fix backend server error",
    )
    d = f.to_dict()
    assert d["test_id"] == "API-001"
    assert d["category"] == "api"
    assert d["tool"] == "httpx"
    assert d["status"] == "failed"
    assert d["severity"] == "high"
    assert d["evidence"]["expected"] == 200
    assert d["recommendation"] == "Fix backend server error"


def test_test_session_standalone_finding():
    """Test adding standalone findings to TestSession."""
    from datetime import datetime
    session = TestSession(session_id="test_1", start_time=datetime.now())
    f = Finding(
        test_id="SEC-001",
        title="Insecure password hashing",
        description="MD5 used",
        category=FindingCategory.SECURITY,
        severity=Severity.CRITICAL,
        url="http://localhost",
    )
    session.add_finding(f)
    assert session.total_findings == 1
    assert len(session.get_all_findings()) == 1
    assert session.findings_by_category["security"] == 1
    assert session.findings_by_severity["critical"] == 1


@patch("httpx.Client.request")
def test_api_tester_success_and_failure(mock_request):
    """Test APITester for status code mismatch and success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_request.return_value = mock_resp

    tester = APITester(base_url="http://localhost:8000")
    findings = tester.test_endpoint("GET", "/health", expected_status=200)

    assert len(findings) == 1
    assert findings[0].category == FindingCategory.API
    assert findings[0].severity == Severity.HIGH
    assert "Status Code Mismatch" in findings[0].title


def test_newman_tester_missing_executable():
    """Test NewmanTester when newman is not installed."""
    with patch("shutil.which", return_value=None):
        tester = NewmanTester(collection_path="nonexistent.json")
        findings = tester.run()
        assert len(findings) == 1
        assert "Newman Executable Not Found" in findings[0].title


def test_code_quality_tester():
    """Test CodeQualityTester execution."""
    tester = CodeQualityTester(target_dir=".")
    findings = tester.run_ruff()
    assert isinstance(findings, list)


def test_security_tester():
    """Test SecurityTester execution."""
    tester = SecurityTester(target_dir=".")
    findings = tester.run_bandit()
    assert isinstance(findings, list)


def test_project_health_tester(tmp_path):
    """Test ProjectHealthTester syntax checking."""
    bad_py = tmp_path / "bad.py"
    bad_py.write_text("def broken_func(:\n    pass\n", encoding="utf-8")

    tester = ProjectHealthTester(target_dir=str(tmp_path))
    findings = tester.check_python_syntax()
    assert len(findings) == 1
    assert "Syntax Error" in findings[0].title
