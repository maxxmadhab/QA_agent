import time
import warnings

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import CustomStep, Finding, StepAction, StepAssertion, TestPlan
from .base import BaseTester


class CustomTester(BaseTester):
    """Executes the :class:`~qa_agent.models.CustomStep` entries in a :class:`~qa_agent.models.TestPlan`.

    Each step consists of a sequence of *actions* (navigation, clicks, form
    fills, etc.) followed by *assertions*.  A failed assertion produces a
    :class:`~qa_agent.models.Finding` with the severity and category specified
    in the step.

    Navigation actions are restored after each step so the page is in a known
    state for subsequent steps and for the standard testers that follow.
    """

    def __init__(self, page: Page, config: TestConfig, test_plan: TestPlan) -> None:
        super().__init__(page, config)
        self.test_plan = test_plan
        self.execution_results: list[dict] = []

    # ------------------------------------------------------------------
    # BaseTester interface
    # ------------------------------------------------------------------

    def run(self) -> list[Finding]:
        """Execute all custom steps and return any findings."""
        if self.page is None:
            return []
        self.findings = []
        self.execution_results = []

        for idx, step in enumerate(self.test_plan.custom_steps, start=1):
            self._execute_step(step, step_num=idx)

        return self.findings

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(self, step: CustomStep, step_num: int = 1) -> None:
        """Execute one step: run all actions, then check all assertions.

        The page URL is restored after the step completes so that navigate
        actions don't corrupt the state for subsequent steps.  If any action
        raises, a Finding is recorded and the rest of the step is skipped.
        """
        if self.page is None:
            return
        original_url = self.page.url
        action_log: list[str] = []
        step_results: list[dict] = []
        assertion_results: list[dict] = []
        case_findings: list[Finding] = []
        case_status = "passed"
        t0 = time.perf_counter()

        # Extract test case id if present in description prefix e.g. "[TC-001] Title"
        case_id = f"TC-{step_num:03d}"
        title = step.description
        if title.startswith("[") and "]" in title:
            prefix, rest = title.split("]", 1)
            case_id = prefix[1:].strip()
            title = rest.strip()

        for a_idx, action in enumerate(step.actions, start=1):
            act_t0 = time.perf_counter()
            try:
                log_line = self._execute_action(action)
                act_duration = (time.perf_counter() - act_t0) * 1000
                action_log.append(log_line)
                step_results.append({
                    "step_index": a_idx,
                    "action": action.type,
                    "target": action.selector,
                    "value": action.value,
                    "status": "passed",
                    "duration_ms": round(act_duration, 2),
                    "description": action.description or log_line,
                    "screenshot_path": None,
                })
            except Exception as exc:
                act_duration = (time.perf_counter() - act_t0) * 1000
                msg = f"{action.type} action failed: {exc}"
                action_log.append(msg)
                case_status = "error"
                ss_path = self._take_screenshot("custom_action_failure")
                step_results.append({
                    "step_index": a_idx,
                    "action": action.type,
                    "target": action.selector,
                    "value": action.value,
                    "status": "error",
                    "duration_ms": round(act_duration, 2),
                    "error_message": msg,
                    "screenshot_path": ss_path,
                    "description": action.description or msg,
                })
                finding = Finding(
                    title=f"Custom step action failed: {step.description}",
                    description=msg,
                    category=step.category,
                    severity=step.severity,
                    url=self.page.url,
                    steps_to_reproduce=action_log,
                    expected_behavior=action.description or f"Action '{action.type}' should succeed",
                    actual_behavior=msg,
                    screenshot_path=ss_path,
                )
                self.findings.append(finding)
                case_findings.append(finding)
                self.execution_results.append({
                    "id": case_id,
                    "title": title,
                    "status": case_status,
                    "total_duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "step_results": step_results,
                    "assertion_results": assertion_results,
                    "findings": [f.to_dict() for f in case_findings],
                })
                return  # Abort — assertions would run on broken state

        for as_idx, assertion in enumerate(step.assertions, start=1):
            as_t0 = time.perf_counter()
            finding, as_result = self._check_assertion_with_result(as_idx, assertion, step, action_log, as_t0)
            assertion_results.append(as_result)
            if finding:
                case_status = "failed"
                self.findings.append(finding)
                case_findings.append(finding)

        self.execution_results.append({
            "id": case_id,
            "title": title,
            "status": case_status,
            "total_duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            "step_results": step_results,
            "assertion_results": assertion_results,
            "findings": [f.to_dict() for f in case_findings],
        })

        # Best-effort restore: navigate back if actions moved us to a different URL
        if self.page.url != original_url:
            try:
                self.page.goto(original_url, wait_until="domcontentloaded")
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass


    def _execute_action(self, action: StepAction) -> str:
        """Perform one action.  Returns a description string; raises on failure."""
        assert self.page is not None
        if action.type == "click":
            if action.selector:
                self.page.locator(action.selector).first.click(timeout=5000)
            return f"Clicked '{action.selector}'"

        if action.type == "fill":
            if action.selector and action.value is not None:
                self.page.locator(action.selector).first.fill(action.value, timeout=5000)
            return f"Filled '{action.selector}' with '{action.value}'"

        if action.type == "hover":
            if action.selector:
                self.page.locator(action.selector).first.hover(timeout=5000)
            return f"Hovered over '{action.selector}'"

        if action.type == "press_key":
            key = action.value or ""
            if action.selector:
                self.page.locator(action.selector).first.press(key, timeout=5000)
            else:
                self.page.keyboard.press(key)
            return f"Pressed key '{key}'"

        if action.type == "wait":
            ms = int(action.value) if action.value and action.value.isdigit() else 1000
            self.page.wait_for_timeout(ms)
            return f"Waited {ms}ms"

        if action.type == "navigate":
            if action.value:
                self.page.goto(action.value, wait_until="domcontentloaded")
                self.page.wait_for_load_state("networkidle", timeout=10000)
            return f"Navigated to '{action.value}'"

        if action.type == "scroll":
            if action.selector:
                self.page.locator(action.selector).first.scroll_into_view_if_needed(timeout=5000)
                return f"Scrolled '{action.selector}' into view"
            direction = action.value or "down"
            delta = 300 if direction != "up" else -300
            self.page.mouse.wheel(0, delta)
            return f"Scrolled page {direction}"

        # Unknown action type — warn but don't raise so the step can continue
        warnings.warn(f"Unknown custom action type '{action.type}' — skipped", stacklevel=2)
        return f"Unknown action type '{action.type}' (skipped)"

    # ------------------------------------------------------------------
    # Assertion checking
    # ------------------------------------------------------------------

    def _check_assertion(
        self,
        assertion: StepAssertion,
        step: CustomStep,
        action_log: list[str],
    ) -> Finding | None:
        """Evaluate one assertion.  Returns a Finding only when it *fails*."""
        finding, _ = self._check_assertion_with_result(1, assertion, step, action_log, time.perf_counter())
        return finding

    def _check_assertion_with_result(
        self,
        as_idx: int,
        assertion: StepAssertion,
        step: CustomStep,
        action_log: list[str],
        as_t0: float,
    ) -> tuple[Finding | None, dict]:
        """Evaluate one assertion, returning both a Finding (if failed) and a structured result dict."""
        assert self.page is not None
        actual_value: str | None = None
        error_msg: str | None = None
        atype = assertion.type

        try:
            # Capture actual values for rich diagnosis
            if atype in ("visible", "hidden") and assertion.selector:
                vis = self.page.locator(assertion.selector).first.is_visible()
                actual_value = "visible" if vis else "hidden"
            elif atype == "text_contains" and assertion.selector:
                actual_value = self.page.locator(assertion.selector).first.text_content() or ""
            elif atype == "url_contains":
                actual_value = self.page.url
            elif atype == "element_count" and assertion.selector:
                actual_value = str(self.page.locator(assertion.selector).count())

            passed = self._evaluate_assertion(assertion)
        except Exception as exc:
            passed = False
            error_msg = f"Evaluation error: {exc}"
            assertion = StepAssertion(
                type=assertion.type,
                selector=assertion.selector,
                value=assertion.value,
                description=f"{assertion.description or assertion.type} — {error_msg}",
            )

        duration_ms = round((time.perf_counter() - as_t0) * 1000, 2)

        if passed:
            return None, {
                "assertion_index": as_idx,
                "type": assertion.type,
                "target": assertion.selector,
                "expected_value": assertion.value,
                "actual_value": actual_value,
                "status": "passed",
                "duration_ms": duration_ms,
                "description": assertion.description or f"Assertion '{assertion.type}' should pass",
                "screenshot_path": None,
            }

        parts = [f"Assertion '{assertion.type}' failed"]
        if assertion.selector:
            parts.append(f"for selector '{assertion.selector}'")
        if assertion.value:
            parts.append(f"(expected: '{assertion.value}')")
        if actual_value is not None:
            parts.append(f"(got: '{actual_value}')")
        if error_msg:
            parts.append(f"({error_msg})")
        failure_msg = " ".join(parts)

        screenshot_path = self._take_screenshot("custom_step_failure")
        finding = Finding(
            title=f"Custom check failed: {step.description}",
            description=assertion.description or failure_msg,
            category=step.category,
            severity=step.severity,
            url=self.page.url if self.page else "",
            steps_to_reproduce=action_log,
            expected_behavior=assertion.description or f"Assertion '{assertion.type}' should pass",
            actual_behavior=failure_msg,
            screenshot_path=screenshot_path,
        )

        return finding, {
            "assertion_index": as_idx,
            "type": assertion.type,
            "target": assertion.selector,
            "expected_value": assertion.value,
            "actual_value": actual_value,
            "status": "failed",
            "duration_ms": duration_ms,
            "error_message": failure_msg,
            "screenshot_path": screenshot_path,
            "description": assertion.description or failure_msg,
        }


    def _evaluate_assertion(self, assertion: StepAssertion) -> bool:
        """Return True if the assertion passes, False otherwise."""
        assert self.page is not None
        atype = assertion.type

        if atype == "visible":
            if not assertion.selector:
                return False
            return self.page.locator(assertion.selector).first.is_visible()

        if atype == "hidden":
            if not assertion.selector:
                return False
            return not self.page.locator(assertion.selector).first.is_visible()

        if atype == "text_contains":
            if not assertion.selector or not assertion.value:
                return False
            text = self.page.locator(assertion.selector).first.text_content() or ""
            return assertion.value.lower() in text.lower()

        if atype == "url_contains":
            if not assertion.value:
                return False
            return assertion.value.lower() in self.page.url.lower()

        if atype == "element_count":
            if not assertion.selector or not assertion.value:
                return False
            count = self.page.locator(assertion.selector).count()
            return str(count) == assertion.value

        # Unknown assertion type: warn and pass to avoid false positives from typos
        warnings.warn(
            f"Unknown custom assertion type '{atype}' — treating as passed. "
            "Check your test plan for unsupported assertion types.",
            stacklevel=2,
        )
        return True
