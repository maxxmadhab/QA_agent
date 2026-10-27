"""Tests for Feature 2: Natural Language to Executable Test Cases and OmniKey integration.

Validates:
1. Scenario 1: Successful assertion execution with step-level results & durations.
2. Scenario 2: Failed assertion execution with failure findings and screenshot recording.
3. Scenario 3: Malformed / unsupported LLM output & destructive safety violation handling.
4. OmniKeyClient unit tests with mocked OpenAI-compatible endpoints.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.ai_planner import AIPlannerClient
from qa_agent.config import TestConfig
from qa_agent.llm_client import (
    DEFAULT_MODELS,
    LLMError,
    LLMProvider,
    LLMResponse,
    OmniKeyClient,
    create_llm_client,
)
from qa_agent.models import CustomStep, Finding, StepAction, StepAssertion, TestPlan, TestSession
from qa_agent.nl_models import NLAssertion, NLStep, NLTestCase
from qa_agent.nl_safety import (
    NLSafetyViolation,
    check_safety_string,
    sanitize_and_validate_test_cases,
)
from qa_agent.testers.custom import CustomTester


# ===========================================================================
# 1. OmniKey Client Unit Tests
# ===========================================================================

class TestOmniKeyClient:
    """Unit tests for OmniKeyClient."""

    def test_missing_api_key_raises_llm_error(self, monkeypatch):
        monkeypatch.delenv("OMNIKEY_API_KEY", raising=False)
        with pytest.raises(LLMError) as exc_info:
            OmniKeyClient(api_key=None)
        assert "OmniKey API key not found" in str(exc_info.value)

    def test_client_initialization_with_key_and_custom_base_url(self):
        client = OmniKeyClient(
            api_key="test-key-123",
            base_url="https://mock.omnikey.ai/v1/",
            model="gpt-4o",
        )
        assert client.base_url == "https://mock.omnikey.ai/v1"
        assert client.model == "gpt-4o"
        assert client._api_key == "test-key-123"

    @patch("qa_agent.llm_client._http_get")
    def test_get_models_parses_response(self, mock_get):
        mock_get.return_value = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "claude-3-5-sonnet"},
                {"id": "deepseek-chat"},
            ]
        }
        client = OmniKeyClient(api_key="test-key")
        models = client.get_models()
        assert models == ["gpt-4o", "claude-3-5-sonnet", "deepseek-chat"]
        assert mock_get.called

    @patch("qa_agent.llm_client._http_get")
    def test_verify_connectivity_success(self, mock_get):
        mock_get.return_value = {"data": [{"id": "gpt-4o"}]}
        client = OmniKeyClient(api_key="test-key")
        result = client.verify_connectivity()
        assert result["status"] == "ok"
        assert result["authenticated"] is True
        assert result["available_models_count"] == 1
        assert "test-key" not in str(result)  # Never leak raw key

    @patch("qa_agent.llm_client._http_get")
    def test_verify_connectivity_failure(self, mock_get):
        mock_get.side_effect = LLMError("Connection refused")
        client = OmniKeyClient(api_key="test-key")
        result = client.verify_connectivity()
        assert result["status"] == "error"
        assert result["authenticated"] is False
        assert "Connection refused" in result["error"]
        assert "test-key" not in str(result)

    @patch("qa_agent.llm_client._http_post")
    def test_complete_invokes_chat_completions(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {"message": {"content": '{"summary": "Test", "custom_steps": []}'}}
            ]
        }
        client = OmniKeyClient(api_key="test-key", model="gpt-4o")
        resp = client.complete(system="System instructions", user="User prompt", max_tokens=1000, timeout=30)
        assert isinstance(resp, LLMResponse)
        assert resp.provider == LLMProvider.OMNIKEY
        assert resp.model == "gpt-4o"
        assert '{"summary": "Test"' in resp.text

    def test_create_llm_client_factory_for_omnikey(self):
        client = create_llm_client(LLMProvider.OMNIKEY, model="test-model", api_key="test-key")
        assert isinstance(client, OmniKeyClient)
        assert client.model == "test-model"


# ===========================================================================
# 2. Safety Guardrails & Schema Validation
# ===========================================================================

class TestNLSafety:
    """Tests for safety guardrails and schema validation."""

    def test_destructive_patterns_blocked(self):
        with pytest.raises(NLSafetyViolation, match="destructive/forbidden pattern"):
            check_safety_string("rm -rf /var/www", "test action")

        with pytest.raises(NLSafetyViolation, match="destructive/forbidden pattern"):
            check_safety_string("DROP TABLE users;", "test action")

        with pytest.raises(NLSafetyViolation, match="destructive/forbidden pattern"):
            check_safety_string("eval('alert(1)')", "test action")

        with pytest.raises(NLSafetyViolation, match="destructive/forbidden pattern"):
            check_safety_string("<script>alert(1)</script>", "test target")

    def test_safe_strings_pass(self):
        check_safety_string("#username", "target")
        check_safety_string("Submit form", "description")
        check_safety_string("button[type='submit']", "selector")

    def test_sanitize_and_validate_test_cases_clamps_limits(self):
        raw = {
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": "Valid Login",
                    "steps": [
                        {"action": "fill", "target": "#user", "value": "demo"},
                        {"action": "fill", "target": "#pass", "value": "secret"},
                        {"action": "click", "target": "#submit"},
                    ],
                    "assertions": [
                        {"type": "visible", "target": ".dashboard"},
                    ],
                }
            ]
        }
        cases = sanitize_and_validate_test_cases(raw)
        assert len(cases) == 1
        assert cases[0].id == "TC-001"
        assert len(cases[0].steps) == 3
        assert len(cases[0].assertions) == 1

    def test_unsupported_actions_sanitized_out(self):
        raw = {
            "test_cases": [
                {
                    "id": "TC-002",
                    "title": "Unsupported Action Case",
                    "steps": [
                        {"action": "fly_to_moon", "target": "#space"},
                        {"action": "click", "target": "#real_button"},
                    ],
                    "assertions": [
                        {"type": "teleport_check", "target": "#star"},
                        {"type": "visible", "target": "#header"},
                    ],
                }
            ]
        }
        cases = sanitize_and_validate_test_cases(raw)
        assert len(cases) == 1
        assert len(cases[0].steps) == 1
        assert cases[0].steps[0].action == "click"
        assert len(cases[0].assertions) == 1
        assert cases[0].assertions[0].type == "visible"

    def test_destructive_action_in_test_cases_rejected(self):
        raw = {
            "test_cases": [
                {
                    "id": "TC-003",
                    "title": "Malicious Case",
                    "steps": [
                        {"action": "fill", "target": "#cmd", "value": "rm -rf /"},
                    ],
                    "assertions": [],
                }
            ]
        }
        with pytest.raises(NLSafetyViolation):
            sanitize_and_validate_test_cases(raw)


# ===========================================================================
# 3. Scenario 1: Successful Assertion Execution
# ===========================================================================

class TestScenario1SuccessfulAssertion:
    """Scenario 1: Steps and assertions succeed, status passed, durations recorded."""

    def test_successful_execution_records_step_results_and_durations(self):
        mock_page = MagicMock()
        mock_page.url = "https://example.com/welcome"
        mock_locator = MagicMock()
        mock_locator.is_visible.return_value = True
        mock_locator.text_content.return_value = "Welcome back, Alice!"
        mock_page.locator.return_value.first = mock_locator

        config = TestConfig(urls=["https://example.com"])
        plan = TestPlan(
            summary="Verify welcome header appears",
            custom_steps=[
                CustomStep(
                    description="[TC-001] Welcome banner is visible with expected greeting",
                    actions=[
                        StepAction(type="click", selector="#login-btn", description="Click login"),
                    ],
                    assertions=[
                        StepAssertion(type="visible", selector="#welcome-banner", description="Banner is visible"),
                        StepAssertion(type="text_contains", selector="#welcome-banner", value="Welcome back", description="Greeting text contains expected string"),
                    ],
                )
            ],
        )

        tester = CustomTester(mock_page, config, plan)
        findings = tester.run()

        # No findings should be raised on success
        assert len(findings) == 0

        # Step results must be recorded
        assert len(tester.execution_results) == 1
        res = tester.execution_results[0]
        assert res["id"] == "TC-001"
        assert res["status"] == "passed"
        assert res["total_duration_ms"] >= 0

        assert len(res["step_results"]) == 1
        step_res = res["step_results"][0]
        assert step_res["status"] == "passed"
        assert step_res["action"] == "click"
        assert step_res["duration_ms"] >= 0

        assert len(res["assertion_results"]) == 2
        for as_res in res["assertion_results"]:
            assert as_res["status"] == "passed"
            assert as_res["duration_ms"] >= 0


# ===========================================================================
# 4. Scenario 2: Failed Assertion Execution
# ===========================================================================

class TestScenario2FailedAssertion:
    """Scenario 2: Step executes, assertion fails, records status=failed, screenshot & finding."""

    def test_failed_assertion_produces_finding_and_screenshot(self):
        mock_page = MagicMock()
        mock_page.url = "https://example.com/login"
        mock_locator = MagicMock()
        mock_locator.is_visible.return_value = False  # Failure condition
        mock_page.locator.return_value.first = mock_locator

        config = TestConfig(urls=["https://example.com"])
        plan = TestPlan(
            summary="Verify error alert on bad credentials",
            custom_steps=[
                CustomStep(
                    description="[TC-002] Error alert must be visible on bad credentials",
                    actions=[
                        StepAction(type="click", selector="#submit-btn", description="Click submit"),
                    ],
                    assertions=[
                        StepAssertion(type="visible", selector=".alert-danger", description="Alert is visible"),
                    ],
                )
            ],
        )

        tester = CustomTester(mock_page, config, plan)
        # Mock screenshot capture
        tester._take_screenshot = MagicMock(return_value="screenshots/custom_step_failure.png")

        findings = tester.run()

        # Assertion failure must produce a finding
        assert len(findings) == 1
        finding = findings[0]
        assert "Custom check failed" in finding.title
        assert finding.screenshot_path == "screenshots/custom_step_failure.png"
        assert "Assertion 'visible' failed" in finding.actual_behavior

        # Execution results must record failure
        assert len(tester.execution_results) == 1
        res = tester.execution_results[0]
        assert res["id"] == "TC-002"
        assert res["status"] == "failed"
        assert len(res["assertion_results"]) == 1
        as_res = res["assertion_results"][0]
        assert as_res["status"] == "failed"
        assert as_res["screenshot_path"] == "screenshots/custom_step_failure.png"


# ===========================================================================
# 5. Scenario 3: Malformed & Unsupported Output Handling
# ===========================================================================

class TestScenario3MalformedOutputHandling:
    """Scenario 3: Malformed JSON, truncated JSON recovery, and destructive keyword handling."""

    def test_recovers_from_valid_markdown_wrapped_json(self):
        planner = AIPlannerClient(provider=LLMProvider.OMNIKEY, model="test-model")
        mock_client = MagicMock()
        raw_json = json.dumps({
            "summary": "Sample plan",
            "focus_areas": ["login"],
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": "Check home title",
                    "steps": [{"action": "wait", "value": "100"}],
                    "assertions": [{"type": "url_contains", "expected_value": "example"}],
                }
            ],
            "warnings": [],
        })
        mock_client.complete.return_value = LLMResponse(
            text=f"```json\n{raw_json}\n```",
            provider=LLMProvider.OMNIKEY,
            model="test-model",
        )
        planner._client = mock_client

        plan = planner.plan("Check home page", "https://example.com")
        assert isinstance(plan, TestPlan)
        assert len(plan.custom_steps) == 1
        assert len(plan.nl_test_cases) == 1
        assert plan.nl_test_cases[0]["id"] == "TC-001"

    def test_completely_invalid_json_raises_value_error(self):
        planner = AIPlannerClient(provider=LLMProvider.OMNIKEY, model="test-model")
        mock_client = MagicMock()
        mock_client.complete.return_value = LLMResponse(
            text="Sorry, I am an AI and cannot assist with this.",
            provider=LLMProvider.OMNIKEY,
            model="test-model",
        )
        planner._client = mock_client

        with pytest.raises(ValueError, match="LLM returned invalid JSON"):
            planner.plan("Test instructions", "https://example.com")

    def test_destructive_prompt_output_captured_in_plan_warnings(self):
        planner = AIPlannerClient(provider=LLMProvider.OMNIKEY, model="test-model")
        mock_client = MagicMock()
        malicious_json = json.dumps({
            "summary": "Destructive plan",
            "focus_areas": ["database"],
            "test_cases": [
                {
                    "id": "TC-BAD",
                    "title": "Drop database",
                    "steps": [{"action": "fill", "target": "#q", "value": "DROP TABLE users;"}],
                    "assertions": [],
                }
            ],
            "warnings": [],
        })
        mock_client.complete.return_value = LLMResponse(
            text=malicious_json,
            provider=LLMProvider.OMNIKEY,
            model="test-model",
        )
        planner._client = mock_client

        plan = planner.plan("Destructive instructions", "https://example.com")
        # Safety violation caught and reported in plan.warnings
        assert any("Safety violation" in w for w in plan.warnings)
        assert len(plan.custom_steps) == 0  # Forbidden step not permitted to execute
