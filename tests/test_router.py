import pytest

from bug_triage.models import BugClassification, PreprocessedBugReport
from bug_triage.router import LOW_CONFIDENCE_THRESHOLD, decide_route


def _classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="low",
        sentiment="calm",
        confidence=0.90,
        confidence_reason="Test classification.",
        missing_info=[],
        route="create_developer_summary",
        reasoning="test",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


def _pre(**overrides) -> PreprocessedBugReport:
    defaults = dict(original_text="x", sanitized_text="x")
    defaults.update(overrides)
    return PreprocessedBugReport(**defaults)


@pytest.mark.parametrize(
    "overrides,expected_route",
    [
        # Rule 1: security category -> escalate, regardless of urgency.
        ({"category": "security", "urgency": "low"}, "escalate_to_human"),
        # Rule 1: critical urgency -> escalate, regardless of category.
        ({"category": "bug", "urgency": "critical"}, "escalate_to_human"),
        # Rule 1 takes priority over rule 3 (missing_info ignored when critical/security).
        ({"category": "security", "urgency": "critical", "missing_info": ["version"]}, "escalate_to_human"),
        # Rule 2: low confidence -> low_confidence_review (below 0.60 threshold).
        ({"category": "bug", "urgency": "medium", "confidence": 0.25}, "low_confidence_review"),
        # Rule 2: confidence exactly at threshold is NOT low (threshold is strict <).
        ({"category": "bug", "urgency": "medium", "confidence": 0.60}, "create_developer_summary"),
        # Rule 1 still wins over rule 2: security at low confidence still escalates.
        ({"category": "security", "urgency": "low", "confidence": 0.25}, "escalate_to_human"),
        # Rule 3: missing_info non-empty (with confidence above threshold) -> ask_for_missing_info.
        ({"category": "bug", "urgency": "medium", "missing_info": ["steps_to_reproduce"]}, "ask_for_missing_info"),
        # Rule 3 takes priority over rule 4: a duplicate with missing_info still asks for info first.
        ({"category": "duplicate", "urgency": "low", "missing_info": ["version"]}, "ask_for_missing_info"),
        # Rule 4: duplicate/spam/invalid with no missing_info -> needs_human_approval_to_close.
        ({"category": "duplicate", "urgency": "low"}, "needs_human_approval_to_close"),
        ({"category": "spam", "urgency": "low"}, "needs_human_approval_to_close"),
        ({"category": "invalid", "urgency": "low"}, "needs_human_approval_to_close"),
        # Rule 5: everything else -> create_developer_summary.
        ({"category": "bug", "urgency": "medium"}, "create_developer_summary"),
        ({"category": "feature_request", "urgency": "low"}, "create_developer_summary"),
        ({"category": "performance", "urgency": "high"}, "create_developer_summary"),
        ({"category": "other", "urgency": "low"}, "create_developer_summary"),
    ],
)
def test_decide_route(overrides, expected_route):
    decision = decide_route(_classification(**overrides))
    assert decision.route == expected_route


def test_escalate_to_human_requires_human_but_not_risky():
    decision = decide_route(_classification(category="security", urgency="critical"))
    assert decision.requires_human is True
    assert decision.risky_action is False


def test_low_confidence_review_requires_human_not_risky():
    decision = decide_route(_classification(confidence=0.25))
    assert decision.route == "low_confidence_review"
    assert decision.requires_human is True
    assert decision.risky_action is False


def test_low_confidence_explanation_includes_percentage():
    decision = decide_route(_classification(confidence=0.25))
    assert "25%" in decision.explanation


def test_needs_human_approval_is_risky_and_requires_human():
    decision = decide_route(_classification(category="spam"))
    assert decision.requires_human is True
    assert decision.risky_action is True


def test_ask_for_missing_info_and_developer_summary_are_not_risky():
    ask = decide_route(_classification(category="bug", missing_info=["version"]))
    summary = decide_route(_classification(category="bug"))
    assert ask.requires_human is False
    assert ask.risky_action is False
    assert summary.requires_human is False
    assert summary.risky_action is False


def test_explanation_mentions_missing_fields():
    decision = decide_route(_classification(category="bug", missing_info=["version", "os"]))
    assert "version" in decision.explanation
    assert "os" in decision.explanation


def test_low_confidence_threshold_constant():
    assert LOW_CONFIDENCE_THRESHOLD == 0.60


def test_red_flag_overrides_normal_routing():
    pre = _pre(red_flags_triggered=["RF001"], red_flags_reason="SQL injection detected.")
    classification = _classification(category="bug", urgency="low")
    decision = decide_route(classification, pre)
    assert decision.route == "escalate_to_human"
    assert "RF001" in decision.explanation or "SQL" in decision.explanation


def test_no_red_flags_passes_through():
    pre = _pre(red_flags_triggered=[])
    decision = decide_route(_classification(missing_info=["version"]), pre)
    assert decision.route == "ask_for_missing_info"
