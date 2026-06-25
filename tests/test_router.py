import pytest

from bug_triage.models import BugClassification
from bug_triage.router import decide_route


def _classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="low",
        sentiment="calm",
        confidence="high",
        missing_info=[],
        route="create_developer_summary",
        reasoning="test",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


@pytest.mark.parametrize(
    "overrides,expected_route",
    [
        # Rule 1: security category -> escalate, regardless of urgency.
        ({"category": "security", "urgency": "low"}, "escalate_to_human"),
        # Rule 1: critical urgency -> escalate, regardless of category.
        ({"category": "bug", "urgency": "critical"}, "escalate_to_human"),
        # Rule 1 takes priority over rule 2 (missing_info ignored when critical/security).
        ({"category": "security", "urgency": "critical", "missing_info": ["version"]}, "escalate_to_human"),
        # Rule 2: missing_info non-empty -> ask_for_missing_info.
        ({"category": "bug", "urgency": "medium", "missing_info": ["steps_to_reproduce"]}, "ask_for_missing_info"),
        # Rule 2 takes priority over rule 3: a duplicate with missing_info still asks for info first.
        ({"category": "duplicate", "urgency": "low", "missing_info": ["version"]}, "ask_for_missing_info"),
        # Rule 3: duplicate/spam/invalid with no missing_info -> needs_human_approval_to_close.
        ({"category": "duplicate", "urgency": "low"}, "needs_human_approval_to_close"),
        ({"category": "spam", "urgency": "low"}, "needs_human_approval_to_close"),
        ({"category": "invalid", "urgency": "low"}, "needs_human_approval_to_close"),
        # Rule 4: everything else -> create_developer_summary.
        ({"category": "bug", "urgency": "medium"}, "create_developer_summary"),
        ({"category": "feature_request", "urgency": "low"}, "create_developer_summary"),
        ({"category": "performance", "urgency": "high"}, "create_developer_summary"),
        ({"category": "other", "urgency": "low"}, "create_developer_summary"),
        # Low confidence escalates before missing_info check.
        ({"category": "bug", "urgency": "medium", "confidence": "low"}, "escalate_to_human"),
        # Security/critical still wins even at low confidence.
        ({"category": "security", "urgency": "low", "confidence": "low"}, "escalate_to_human"),
    ],
)
def test_decide_route(overrides, expected_route):
    decision = decide_route(_classification(**overrides))
    assert decision.route == expected_route


def test_escalate_to_human_requires_human_but_not_risky():
    decision = decide_route(_classification(category="security", urgency="critical"))
    assert decision.requires_human is True
    assert decision.risky_action is False


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


def test_low_confidence_escalates_not_risky():
    decision = decide_route(_classification(category="bug", urgency="medium", confidence="low"))
    assert decision.route == "escalate_to_human"
    assert decision.requires_human is True
    assert decision.risky_action is False
    assert "confidence" in decision.explanation.lower()


def test_security_explanation_not_overridden_by_low_confidence():
    decision = decide_route(_classification(category="security", urgency="low", confidence="low"))
    assert decision.route == "escalate_to_human"
    assert "security" in decision.explanation.lower() or "critical" in decision.explanation.lower()
