"""Tests for the deterministic red-flag detection rules in red_flags.py."""

import pytest

from bug_triage.models import BugClassification, PreprocessedBugReport
from bug_triage.red_flags import check_red_flags
from bug_triage.router import decide_route


def _pre(text: str, red_flags: list[str] | None = None) -> PreprocessedBugReport:
    return PreprocessedBugReport(
        original_text=text,
        sanitized_text=text,
        red_flags_triggered=red_flags or [],
    )


def _classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="medium",
        sentiment="calm",
        confidence="high",
        missing_info=[],
        route="create_developer_summary",
        reasoning="test",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


# ── check_red_flags unit tests ────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_rule", [
    ("We found a SQL injection vulnerability in the login form.", "RF001"),
    ("The endpoint is vulnerable to cross-site scripting (XSS).", "RF001"),
    ("Attacker can achieve remote code execution via the upload endpoint.", "RF001"),
    ("The form is susceptible to CSRF attacks.", "RF001"),
    ("A data breach exposed thousands of user records.", "RF002"),
    ("Personal data including emails was leaked in the response.", "RF002"),
    ("This violates GDPR — user PII is visible without authentication.", "RF002"),
    ("The service outage lasted 3 hours and all users were affected.", "RF003"),
    ("Production is down since 09:00 UTC.", "RF003"),
    ("There is an authentication bypass on the admin panel.", "RF004"),
    ("Privilege escalation allows non-admin users to delete accounts.", "RF004"),
    ("A zero-day exploit was discovered in the authentication module.", "RF004"),
    ("Account takeover is possible via the password reset flow.", "RF004"),
])
def test_red_flag_hit(text: str, expected_rule: str):
    triggered = check_red_flags(text)
    rule_ids = [r.rule_id for r in triggered]
    assert expected_rule in rule_ids, f"Expected {expected_rule} to fire for: {text!r}"


@pytest.mark.parametrize("text", [
    "The export button does not work on Windows 11.",
    "App crashes when uploading a 10 MB file.",
    "Dark mode toggle resets after each login.",
    "The chart renders incorrectly on mobile Safari.",
])
def test_no_red_flag_benign_text(text: str):
    assert check_red_flags(text) == []


def test_multiple_rules_can_trigger():
    text = "SQL injection allows account takeover and data breach of PII."
    triggered = check_red_flags(text)
    rule_ids = {r.rule_id for r in triggered}
    assert "RF001" in rule_ids
    assert "RF002" in rule_ids
    assert "RF004" in rule_ids


# ── router integration: red-flag hard override ────────────────────────────────

def test_red_flag_overrides_create_developer_summary():
    pre = _pre("SQL injection found.", red_flags=["RF001"])
    classification = _classification(category="bug", urgency="low")
    decision = decide_route(classification, pre)
    assert decision.route == "escalate_to_human"
    assert "RF001" in decision.explanation


def test_red_flag_overrides_even_without_security_category():
    pre = _pre("Production is down, all users affected.", red_flags=["RF003"])
    classification = _classification(category="performance", urgency="medium")
    decision = decide_route(classification, pre)
    assert decision.route == "escalate_to_human"
    assert "RF003" in decision.explanation


def test_no_red_flags_passes_through_to_normal_routing():
    pre = _pre("App crashes on export.", red_flags=[])
    classification = _classification(category="bug", missing_info=["version"])
    decision = decide_route(classification, pre)
    assert decision.route == "ask_for_missing_info"


def test_decide_route_without_preprocessed_still_works():
    classification = _classification(category="bug", missing_info=["version"])
    decision = decide_route(classification)
    assert decision.route == "ask_for_missing_info"
