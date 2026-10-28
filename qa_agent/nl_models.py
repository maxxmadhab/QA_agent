"""Structured Natural Language Test Case and Execution Outcome models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import CustomStep, FindingCategory, Severity, StepAction, StepAssertion


@dataclass
class NLStep:
    """A single action step in a structured test case."""

    action: str  # click, fill, hover, press_key, wait, scroll, navigate
    target: str | None = None  # CSS selector or target locator
    value: str | None = None  # input value, key, duration ms, or URL
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "description": self.description,
        }

    def to_step_action(self) -> StepAction:
        """Convert to existing StepAction model for CustomTester."""
        return StepAction(
            type=self.action,
            selector=self.target,
            value=self.value,
            description=self.description,
        )


@dataclass
class NLAssertion:
    """An assertion to verify within a structured test case."""

    type: str  # visible, hidden, text_contains, url_contains, element_count
    target: str | None = None  # CSS selector or target locator
    expected_value: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "expected_value": self.expected_value,
            "description": self.description,
        }

    def to_step_assertion(self) -> StepAssertion:
        """Convert to existing StepAssertion model for CustomTester."""
        return StepAssertion(
            type=self.type,
            selector=self.target,
            value=self.expected_value,
            description=self.description,
        )


@dataclass
class NLTestCase:
    """A structured executable test case generated from natural language."""

    id: str
    title: str
    preconditions: list[str] = field(default_factory=list)
    steps: list[NLStep] = field(default_factory=list)
    assertions: list[NLAssertion] = field(default_factory=list)
    severity: str = "medium"
    category: str = "unexpected_behavior"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "preconditions": self.preconditions,
            "steps": [s.to_dict() for s in self.steps],
            "assertions": [a.to_dict() for a in self.assertions],
            "severity": self.severity,
            "category": self.category,
        }

    def to_custom_step(self) -> CustomStep:
        """Convert to existing CustomStep for CustomTester execution."""
        sev_map = {
            "info": Severity.INFO,
            "low": Severity.LOW,
            "medium": Severity.MEDIUM,
            "high": Severity.HIGH,
            "critical": Severity.CRITICAL,
        }
        cat_map = {
            "keyboard_navigation": FindingCategory.KEYBOARD_NAVIGATION,
            "mouse_interaction": FindingCategory.MOUSE_INTERACTION,
            "form_handling": FindingCategory.FORM_HANDLING,
            "accessibility": FindingCategory.ACCESSIBILITY,
            "console_error": FindingCategory.CONSOLE_ERROR,
            "network_error": FindingCategory.NETWORK_ERROR,
            "visual_issue": FindingCategory.VISUAL_ISSUE,
            "performance": FindingCategory.PERFORMANCE,
            "unexpected_behavior": FindingCategory.UNEXPECTED_BEHAVIOR,
        }
        return CustomStep(
            description=self.title,
            actions=[s.to_step_action() for s in self.steps],
            assertions=[a.to_step_assertion() for a in self.assertions],
            severity=sev_map.get(self.severity.lower(), Severity.MEDIUM),
            category=cat_map.get(self.category.lower(), FindingCategory.UNEXPECTED_BEHAVIOR),
        )



@dataclass
class NLStepResult:
    """Outcome of an individual action step execution."""

    step_index: int
    action: str
    target: str | None
    value: str | None
    status: str  # passed, failed, error, skipped
    duration_ms: float
    error_message: str | None = None
    screenshot_path: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "description": self.description,
        }


@dataclass
class NLAssertionResult:
    """Outcome of an individual assertion execution."""

    assertion_index: int
    type: str
    target: str | None
    expected_value: str | None
    actual_value: str | None
    status: str  # passed, failed, error
    duration_ms: float
    error_message: str | None = None
    screenshot_path: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_index": self.assertion_index,
            "type": self.type,
            "target": self.target,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "description": self.description,
        }


@dataclass
class NLTestCaseResult:
    """Complete execution record of a natural language test case."""

    id: str
    title: str
    status: str  # passed, failed, error
    total_duration_ms: float
    step_results: list[NLStepResult] = field(default_factory=list)
    assertion_results: list[NLAssertionResult] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "step_results": [s.to_dict() for s in self.step_results],
            "assertion_results": [a.to_dict() for a in self.assertion_results],
            "findings": self.findings,
            "error_message": self.error_message,
        }
