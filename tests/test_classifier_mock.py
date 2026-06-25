"""Tests for the deterministic mock classifier (BUG_TRIAGE_MOCK_LLM=true path).

These run fully offline - no network access or API key required.
"""

from bug_triage.classifier_agent import _mock_classify
from bug_triage.models import BugReportInput
from bug_triage.preprocess import preprocess
from bug_triage.router import decide_route


def _classify_text(raw_text: str):
    return _mock_classify(preprocess(BugReportInput(raw_text=raw_text)))


def test_security_keyword_escalates():
    classification = _classify_text("There is an authentication bypass vulnerability in the login flow.")
    assert classification.category == "security"
    assert classification.urgency == "critical"
    assert classification.confidence == "high"
    assert decide_route(classification).route == "escalate_to_human"


def test_spam_keyword_needs_approval():
    classification = _classify_text("Get 50% off premium subscriptions, use this promo code now!")
    assert classification.category == "spam"
    assert classification.confidence == "high"
    assert decide_route(classification).route == "needs_human_approval_to_close"


def test_issue_reference_is_duplicate():
    classification = _classify_text("This is the same as ticket #4821, already reported last month.")
    assert classification.category == "duplicate"
    assert classification.confidence == "high"
    assert classification.missing_info == []
    assert decide_route(classification).route == "needs_human_approval_to_close"


def test_vague_report_low_confidence_escalates_to_human():
    # Report missing version, OS, steps, expected/actual (4 fields) → low confidence → escalate.
    classification = _classify_text("The app crashes sometimes, it's really annoying, please fix ASAP.")
    assert classification.category == "bug"
    assert classification.missing_info != []
    assert classification.confidence == "low"
    assert decide_route(classification).route == "escalate_to_human"


def test_partial_report_medium_confidence_asks_for_info():
    # Has version + OS + steps, only missing expected/actual (1-2 fields) → medium confidence → ask.
    raw_text = (
        "App crashes on Windows 11 v4.12.1.\n"
        "Steps to reproduce: open the app and click Export.\n"
        "Actual: the app crashes immediately.\n"
    )
    classification = _classify_text(raw_text)
    assert classification.category == "bug"
    assert classification.confidence in ("medium", "high")
    assert decide_route(classification).route == "ask_for_missing_info"


def test_complete_report_creates_developer_summary():
    raw_text = (
        "Export to CSV fails on rows with commas.\n"
        "Steps to reproduce: add a record with a comma in Notes, then export.\n"
        "Expected: the row is quoted correctly.\n"
        "Actual: the export raises an error.\n"
        "Environment: Web app v4.12.1, Windows 11.\n"
    )
    classification = _classify_text(raw_text)
    assert classification.category == "bug"
    assert classification.confidence == "high"
    assert classification.missing_info == []
    assert decide_route(classification).route == "create_developer_summary"
