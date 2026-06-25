"""Tests for the deterministic mock classifier (BUG_TRIAGE_MOCK_LLM=true path).

These run fully offline - no network access or API key required.
"""

from bug_triage.classifier_agent import _CONFIDENCE_STRONG_SIGNAL, _CONFIDENCE_VAGUE, _mock_classify
from bug_triage.models import BugReportInput
from bug_triage.preprocess import preprocess
from bug_triage.router import LOW_CONFIDENCE_THRESHOLD, decide_route


def _classify_text(raw_text: str):
    return _mock_classify(preprocess(BugReportInput(raw_text=raw_text)))


def test_security_keyword_high_confidence():
    classification = _classify_text("There is an authentication bypass vulnerability in the login flow.")
    assert classification.category == "security"
    assert classification.urgency == "critical"
    assert classification.confidence == _CONFIDENCE_STRONG_SIGNAL
    assert classification.confidence >= LOW_CONFIDENCE_THRESHOLD
    assert decide_route(classification).route == "escalate_to_human"


def test_security_can_have_high_confidence_and_still_escalate():
    # Security always escalates regardless of confidence level — tested explicitly.
    classification = _classify_text("SQL injection found in the login form. OS: Windows. Version v2.0.")
    assert classification.category == "security"
    assert classification.confidence >= LOW_CONFIDENCE_THRESHOLD
    assert decide_route(classification).route == "escalate_to_human"


def test_spam_keyword_high_confidence():
    classification = _classify_text("Get 50% off premium subscriptions, use this promo code now!")
    assert classification.category == "spam"
    assert classification.confidence == _CONFIDENCE_STRONG_SIGNAL
    assert decide_route(classification).route == "needs_human_approval_to_close"


def test_issue_reference_is_duplicate_high_confidence():
    classification = _classify_text("This is the same as ticket #4821, already reported last month.")
    assert classification.category == "duplicate"
    assert classification.confidence == _CONFIDENCE_STRONG_SIGNAL
    assert classification.missing_info == []
    assert decide_route(classification).route == "needs_human_approval_to_close"


def test_vague_report_low_confidence_routes_to_review():
    # 4 missing fields → confidence = 0.25 (below 0.60 threshold) → low_confidence_review.
    classification = _classify_text("The app crashes sometimes, it's really annoying, please fix ASAP.")
    assert classification.category == "bug"
    assert classification.missing_info != []
    assert classification.confidence == _CONFIDENCE_VAGUE
    assert classification.confidence < LOW_CONFIDENCE_THRESHOLD
    assert decide_route(classification).route == "low_confidence_review"


def test_partial_report_above_threshold_asks_for_info():
    # Has version + OS + steps, missing only expected/actual (1 field) → confidence 0.70 → ask.
    raw_text = (
        "App crashes on Windows 11 v4.12.1.\n"
        "Steps to reproduce: open the app and click Export.\n"
        "Actual: the app crashes immediately.\n"
    )
    classification = _classify_text(raw_text)
    assert classification.category == "bug"
    assert classification.confidence >= LOW_CONFIDENCE_THRESHOLD
    assert decide_route(classification).route == "ask_for_missing_info"


def test_complete_report_high_confidence_developer_summary():
    raw_text = (
        "Export to CSV fails on rows with commas.\n"
        "Steps to reproduce: add a record with a comma in Notes, then export.\n"
        "Expected: the row is quoted correctly.\n"
        "Actual: the export raises an error.\n"
        "Environment: Web app v4.12.1, Windows 11.\n"
    )
    classification = _classify_text(raw_text)
    assert classification.category == "bug"
    assert classification.confidence >= 0.85
    assert classification.missing_info == []
    assert decide_route(classification).route == "create_developer_summary"


def test_confidence_reason_is_present():
    classification = _classify_text("App crashes. No other details.")
    assert isinstance(classification.confidence_reason, str)
    assert len(classification.confidence_reason) > 0
