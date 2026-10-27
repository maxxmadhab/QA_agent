"""Safety guardrails and schema validation for AI-generated test cases."""

from __future__ import annotations

import re
from typing import Any

from .nl_models import NLAssertion, NLStep, NLTestCase

# Forbidden keywords indicating destructive or arbitrary code execution attempts
_DESTRUCTIVE_PATTERNS = [
    re.compile(r"\b(rm\s+-rf|del\s+/[fqs]|format\s+[a-z]:)\b", re.IGNORECASE),
    re.compile(r"\b(drop\s+table|delete\s+from|truncate\s+table|update\s+\w+\s+set)\b", re.IGNORECASE),
    re.compile(r"(\bexec\s*\(|\beval\s*\(|\b__import__\b|\bsubprocess\b|\bos\.system\b|\bos\.popen\b)", re.IGNORECASE),
    re.compile(r"(<script[\s>]|javascript:|data:text/html)", re.IGNORECASE),

    re.compile(r"\b(payment|credit_card|cvv|expire_date|purge|wipe_database)\b", re.IGNORECASE),
]

_SUPPORTED_ACTIONS = frozenset({
    "click", "fill", "hover", "press_key", "wait", "scroll", "navigate"
})

_SUPPORTED_ASSERTIONS = frozenset({
    "visible", "hidden", "text_contains", "url_contains", "element_count"
})

MAX_TEST_CASES = 10
MAX_STEPS_PER_CASE = 20
MAX_WAIT_MS = 10000


class NLSafetyViolation(ValueError):
    """Raised when an AI test case violates safety guardrails."""
    pass


def check_safety_string(text: str | None, context: str) -> None:
    """Verify that a string does not contain destructive commands or script injection."""
    if not text:
        return
    for pattern in _DESTRUCTIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            raise NLSafetyViolation(
                f"Safety violation in {context}: destructive/forbidden pattern '{match.group(0)}' detected."
            )


def sanitize_and_validate_test_cases(raw_data: Any) -> list[NLTestCase]:
    """Parse, sanitize, and validate raw LLM output into safe NLTestCase instances.

    Accepts:
    - dict with "test_cases" array
    - list of test case dicts
    - dict with "custom_steps" (backward compatibility)

    Enforces:
    - Max 10 test cases
    - Max 20 steps per test case
    - No destructive actions or code execution
    - Known actions and assertions only (unsupported are sanitized or flagged)
    """
    if not isinstance(raw_data, (dict, list)):
        raise NLSafetyViolation(f"Expected dict or list for test cases, got {type(raw_data).__name__}")

    raw_cases: list[dict] = []
    if isinstance(raw_data, list):
        raw_cases = raw_data
    elif "test_cases" in raw_data and isinstance(raw_data["test_cases"], list):
        raw_cases = raw_data["test_cases"]
    elif "test_plan" in raw_data and isinstance(raw_data["test_plan"], list):
        for idx, item in enumerate(raw_data["test_plan"], start=1):
            raw_cases.append({
                "id": item.get("id", f"TC-{idx:03d}"),
                "title": item.get("title") or item.get("scenario") or item.get("description") or f"Test Case {idx}",
                "severity": item.get("severity", "medium"),
                "category": item.get("category", "unexpected_behavior"),
                "steps": item.get("steps") or item.get("actions") or [],
                "assertions": item.get("assertions") or [],
            })
    elif "scenarios" in raw_data and isinstance(raw_data["scenarios"], list):
        for idx, item in enumerate(raw_data["scenarios"], start=1):
            raw_cases.append({
                "id": item.get("id", f"TC-{idx:03d}"),
                "title": item.get("title") or item.get("name") or item.get("scenario") or item.get("description") or f"Test Case {idx}",
                "severity": item.get("severity", "medium"),
                "category": item.get("category", "unexpected_behavior"),
                "steps": item.get("steps") or item.get("actions") or [],
                "assertions": item.get("assertions") or [],
            })

    elif "custom_steps" in raw_data and isinstance(raw_data["custom_steps"], list):
        # Convert legacy custom_steps to test cases
        for idx, cs in enumerate(raw_data["custom_steps"], start=1):
            raw_cases.append({
                "id": f"TC-{idx:03d}",
                "title": cs.get("description", f"Test Case {idx}"),
                "severity": cs.get("severity", "medium"),
                "category": cs.get("category", "unexpected_behavior"),
                "steps": [
                    {
                        "action": a.get("type") or a.get("action"),
                        "target": a.get("selector") or a.get("target"),
                        "value": a.get("value"),
                        "description": a.get("description"),
                    }
                    for a in cs.get("actions", [])
                ],
                "assertions": [
                    {
                        "type": a.get("type"),
                        "target": a.get("selector") or a.get("target"),
                        "expected_value": a.get("value") or a.get("expected_value"),
                        "description": a.get("description"),
                    }
                    for a in cs.get("assertions", [])
                ],
            })
    else:
        raise NLSafetyViolation("No 'test_cases', 'test_plan', or 'custom_steps' found in AI output.")

    if len(raw_cases) > MAX_TEST_CASES:
        raw_cases = raw_cases[:MAX_TEST_CASES]

    validated_cases: list[NLTestCase] = []

    for idx, c in enumerate(raw_cases, start=1):
        if not isinstance(c, dict):
            continue

        case_id = str(c.get("id") or f"TC-{idx:03d}").strip()
        title = str(c.get("title") or c.get("scenario") or c.get("description") or f"Test Case {idx}").strip()

        check_safety_string(case_id, f"test case {case_id} id")
        check_safety_string(title, f"test case {case_id} title")

        preconditions = [
            str(p).strip() for p in c.get("preconditions", [])
            if isinstance(p, (str, int)) and str(p).strip()
        ]
        for p in preconditions:
            check_safety_string(p, f"test case {case_id} precondition")

        # Process steps & assertions
        raw_steps = c.get("steps") or c.get("actions") or []
        if not isinstance(raw_steps, list):
            raw_steps = []

        if len(raw_steps) > MAX_STEPS_PER_CASE:
            raw_steps = raw_steps[:MAX_STEPS_PER_CASE]

        steps: list[NLStep] = []
        assertions: list[NLAssertion] = []

        for s_idx, s in enumerate(raw_steps, start=1):
            if not isinstance(s, dict):
                continue

            action = str(s.get("action") or s.get("type") or "").strip().lower()
            target = s.get("target") or s.get("selector")
            value = s.get("value")
            desc = s.get("description")

            # Translate common verification actions to assertions
            if action in ("check_element_presence", "verify_visible", "assert_visible", "is_visible"):
                if target:
                    check_safety_string(str(target), f"{case_id} step {s_idx} target")
                assertions.append(NLAssertion(type="visible", target=str(target) if target else None, description=desc))
                continue
            elif action in ("check_text", "verify_text", "assert_text"):
                if target:
                    check_safety_string(str(target), f"{case_id} step {s_idx} target")
                assertions.append(NLAssertion(type="text_contains", target=str(target) if target else None, expected_value=str(value) if value else None, description=desc))
                continue

            if action not in _SUPPORTED_ACTIONS:
                # Sanitize / skip unsupported action
                continue


            target = s.get("target") or s.get("selector")
            if target is not None:
                target = str(target).strip()
                check_safety_string(target, f"{case_id} step {s_idx} target")

            value = s.get("value")
            if value is not None:
                value = str(value).strip()
                check_safety_string(value, f"{case_id} step {s_idx} value")

            # Clamp wait times
            if action == "wait":
                try:
                    ms = int(value or "1000")
                    value = str(min(MAX_WAIT_MS, max(50, ms)))
                except (ValueError, TypeError):
                    value = "1000"

            desc = s.get("description")
            if desc is not None:
                desc = str(desc).strip()
                check_safety_string(desc, f"{case_id} step {s_idx} description")

            steps.append(NLStep(action=action, target=target, value=value, description=desc))

        # Process assertions
        raw_assertions = c.get("assertions") or []
        if not isinstance(raw_assertions, list):
            raw_assertions = []

        assertions: list[NLAssertion] = []
        for a_idx, a in enumerate(raw_assertions, start=1):
            if not isinstance(a, dict):
                continue

            atype = str(a.get("type") or "").strip().lower()
            if atype not in _SUPPORTED_ASSERTIONS:
                continue

            target = a.get("target") or a.get("selector")
            if target is not None:
                target = str(target).strip()
                check_safety_string(target, f"{case_id} assertion {a_idx} target")

            expected_value = a.get("expected_value") or a.get("value")
            if expected_value is not None:
                expected_value = str(expected_value).strip()
                check_safety_string(expected_value, f"{case_id} assertion {a_idx} expected_value")

            desc = a.get("description")
            if desc is not None:
                desc = str(desc).strip()
                check_safety_string(desc, f"{case_id} assertion {a_idx} description")

            assertions.append(
                NLAssertion(
                    type=atype,
                    target=target,
                    expected_value=expected_value,
                    description=desc,
                )
            )

        severity = str(c.get("severity") or "medium").strip().lower()
        if severity not in {"info", "low", "medium", "high", "critical"}:
            severity = "medium"

        category = str(c.get("category") or "unexpected_behavior").strip().lower()

        validated_cases.append(
            NLTestCase(
                id=case_id,
                title=title,
                preconditions=preconditions,
                steps=steps,
                assertions=assertions,
                severity=severity,
                category=category,
            )
        )

    return validated_cases

