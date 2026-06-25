"""Tests for the deterministic red-flag detection rules."""

import pytest

from bug_triage.models import BugClassification, PreprocessedBugReport
from bug_triage.red_flags import RedFlagResult, check_red_flags, evaluate_red_flags
from bug_triage.router import decide_route


def _pre(text: str, red_flags: list[str] | None = None, reason: str | None = None) -> PreprocessedBugReport:
    return PreprocessedBugReport(
        original_text=text,
        sanitized_text=text,
        red_flags_triggered=red_flags or [],
        red_flags_reason=reason,
    )


def _classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="medium",
        sentiment="calm",
        confidence=0.90,
        confidence_reason="Test classification.",
        missing_info=[],
        route="create_developer_summary",
        reasoning="test",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


# ── check_red_flags unit tests ────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_rule", [
    # RF001 — security attack vectors
    ("We found a SQL injection vulnerability in the login form.", "RF001"),
    ("The endpoint is vulnerable to cross-site scripting (XSS).", "RF001"),
    ("Attacker can achieve remote code execution via the upload endpoint.", "RF001"),
    ("The form is susceptible to CSRF attacks.", "RF001"),
    ("The API key was exposed in the response body.", "RF001"),
    ("Auth token leaked in the server logs.", "RF001"),
    # RF002 — data risk
    ("A data breach exposed thousands of user records.", "RF002"),
    ("Personal data including emails was visible in the response.", "RF002"),
    ("This violates GDPR — user PII is visible without authentication.", "RF002"),
    ("Users can see other users' data on the dashboard.", "RF002"),
    ("Data loss occurred during the migration.", "RF002"),
    # RF003 — production impact
    ("The service outage lasted 3 hours and all users were affected.", "RF003"),
    ("Production is down since 09:00 UTC.", "RF003"),
    ("No one can log in since the last deployment.", "RF003"),
    # RF004 — auth risk
    ("There is an authentication bypass on the admin panel.", "RF004"),
    ("Privilege escalation allows non-admin users to delete accounts.", "RF004"),
    ("A zero-day exploit was discovered in the authentication module.", "RF004"),
    ("Account takeover is possible via the password reset flow.", "RF004"),
    # RF005 — payment risk
    ("I was double charged for my subscription.", "RF005"),
    ("The system charged me twice for the same order.", "RF005"),
    ("There was an unauthorized charge on my account.", "RF005"),
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
    "I would like to request a refund for my subscription.",  # refund ≠ double charge
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


# ── evaluate_red_flags ────────────────────────────────────────────────────────

def test_evaluate_no_flags():
    result = evaluate_red_flags("App crashes on export.")
    assert isinstance(result, RedFlagResult)
    assert result.flags == []
    assert result.forced_route is None
    assert result.reason is None


def test_evaluate_single_flag():
    result = evaluate_red_flags("SQL injection found in the login form.")
    assert "RF001" in result.flags
    assert result.forced_route == "escalate_to_human"
    assert result.reason is not None
    assert "RF001" in result.reason


def test_evaluate_multiple_flags():
    result = evaluate_red_flags("Data breach via SQL injection, all users affected.")
    assert len(result.flags) >= 2
    assert result.forced_route == "escalate_to_human"


# ── router integration ────────────────────────────────────────────────────────

def test_red_flag_overrides_create_developer_summary():
    pre = _pre("SQL injection found.", red_flags=["RF001"], reason="RF001 triggered.")
    decision = decide_route(_classification(category="bug", urgency="low"), pre)
    assert decision.route == "escalate_to_human"
    assert "RF001" in decision.explanation or "SQL" in decision.explanation


def test_red_flag_overrides_even_without_security_category():
    pre = _pre("I was double charged.", red_flags=["RF005"], reason="RF005 triggered.")
    decision = decide_route(_classification(category="performance", urgency="medium"), pre)
    assert decision.route == "escalate_to_human"


def test_red_flag_priority_beats_low_confidence():
    pre = _pre("Data breach!", red_flags=["RF002"], reason="RF002 triggered.")
    # Even low confidence doesn't change the outcome — red flags fire first.
    decision = decide_route(_classification(confidence=0.10), pre)
    assert decision.route == "escalate_to_human"


def test_no_red_flags_passes_through_to_normal_routing():
    pre = _pre("App crashes on export.", red_flags=[])
    decision = decide_route(_classification(missing_info=["version"]), pre)
    assert decision.route == "ask_for_missing_info"


def test_decide_route_without_preprocessed_still_works():
    decision = decide_route(_classification(missing_info=["version"]))
    assert decision.route == "ask_for_missing_info"
