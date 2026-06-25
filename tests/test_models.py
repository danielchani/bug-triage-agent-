import pytest
from pydantic import ValidationError

from bug_triage.models import (
    ApprovalRequest,
    BugClassification,
    BugReportInput,
    ClassifiedBugReport,
    PreprocessedBugReport,
    RouteDecision,
    RoutedBugReport,
)


def test_bug_report_input_defaults():
    report = BugReportInput(raw_text="App crashes on launch")
    assert report.raw_text == "App crashes on launch"
    assert report.source is None
    assert report.received_at is None


def test_preprocessed_bug_report_defaults():
    pre = PreprocessedBugReport(original_text="hello", sanitized_text="hello")
    assert pre.extracted_email is None
    assert pre.extracted_issue_id is None
    assert pre.extracted_version is None
    assert pre.extracted_os is None
    assert pre.has_stack_trace is False
    assert pre.red_flags_triggered == []
    assert pre.red_flags_reason is None


def test_bug_classification_valid():
    classification = BugClassification(
        category="security",
        urgency="critical",
        sentiment="calm",
        confidence=0.95,
        confidence_reason="Unambiguous security keyword match.",
        missing_info=[],
        route="escalate_to_human",
        reasoning="Auth bypass is a critical security issue.",
    )
    assert classification.category == "security"
    assert classification.confidence == 0.95
    assert classification.confidence_reason == "Unambiguous security keyword match."
    assert classification.missing_info == []


def test_bug_classification_confidence_bounds():
    with pytest.raises(ValidationError):
        BugClassification(
            category="bug",
            urgency="low",
            sentiment="calm",
            confidence=1.5,  # above 1.0
            confidence_reason="x",
            route="create_developer_summary",
            reasoning="x",
        )
    with pytest.raises(ValidationError):
        BugClassification(
            category="bug",
            urgency="low",
            sentiment="calm",
            confidence=-0.1,  # below 0.0
            confidence_reason="x",
            route="create_developer_summary",
            reasoning="x",
        )


def test_bug_classification_rejects_invalid_category():
    with pytest.raises(ValidationError):
        BugClassification(
            category="not-a-real-category",
            urgency="low",
            sentiment="calm",
            confidence=0.9,
            confidence_reason="test",
            route="create_developer_summary",
            reasoning="x",
        )


def test_bug_classification_rejects_invalid_route():
    with pytest.raises(ValidationError):
        BugClassification(
            category="bug",
            urgency="low",
            sentiment="calm",
            confidence=0.9,
            confidence_reason="test",
            route="not-a-real-route",
            reasoning="x",
        )


def test_route_decision_construction():
    decision = RouteDecision(
        route="needs_human_approval_to_close",
        requires_human=True,
        risky_action=True,
        explanation="Looks like a duplicate report.",
    )
    assert decision.requires_human is True
    assert decision.risky_action is True


def test_low_confidence_review_is_valid_route():
    decision = RouteDecision(
        route="low_confidence_review",
        requires_human=True,
        risky_action=False,
        explanation="Below confidence threshold.",
    )
    assert decision.route == "low_confidence_review"


def test_classified_and_routed_bug_report_roundtrip():
    pre = PreprocessedBugReport(original_text="hello", sanitized_text="hello")
    classification = BugClassification(
        category="bug",
        urgency="medium",
        sentiment="calm",
        confidence=0.65,
        confidence_reason="Two fields missing.",
        missing_info=["steps_to_reproduce"],
        route="ask_for_missing_info",
        reasoning="Not enough detail.",
    )
    classified = ClassifiedBugReport(preprocessed=pre, classification=classification)
    assert classified.preprocessed.original_text == "hello"

    decision = RouteDecision(
        route="ask_for_missing_info",
        requires_human=False,
        risky_action=False,
        explanation="Missing info requested.",
    )
    routed = RoutedBugReport(preprocessed=pre, classification=classification, decision=decision)
    assert routed.decision.route == "ask_for_missing_info"
    assert routed.classification.missing_info == ["steps_to_reproduce"]


def test_approval_request_dataclass():
    request = ApprovalRequest(
        summary="Dark mode resets after login",
        category="duplicate",
        proposed_action="Close this report as duplicate.",
        reasoning="References ticket #4821.",
    )
    assert request.category == "duplicate"
    assert "duplicate" in request.proposed_action
