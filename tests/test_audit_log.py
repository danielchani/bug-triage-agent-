"""Tests for the JSONL audit log (audit_log.py)."""

import json
from pathlib import Path

from bug_triage.audit_log import append_audit_entry, build_audit_entry
from bug_triage.models import BugClassification, PreprocessedBugReport, RouteDecision


def _make_classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="medium",
        sentiment="calm",
        confidence=0.90,
        confidence_reason="All fields present.",
        missing_info=[],
        route="create_developer_summary",
        reasoning="Complete report.",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


def _make_preprocessed(**overrides) -> PreprocessedBugReport:
    defaults = dict(original_text="hello world", sanitized_text="hello world")
    defaults.update(overrides)
    return PreprocessedBugReport(**defaults)


def _make_decision(**overrides) -> RouteDecision:
    defaults = dict(
        route="create_developer_summary",
        requires_human=False,
        risky_action=False,
        explanation="Actionable report.",
    )
    defaults.update(overrides)
    return RouteDecision(**defaults)


def test_build_audit_entry_fields():
    entry = build_audit_entry(
        input_source="samples/complete_bug.txt",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=_make_preprocessed(),
    )
    assert entry.input_source == "samples/complete_bug.txt"
    assert entry.category == "bug"
    assert entry.urgency == "medium"
    assert entry.confidence == 0.90
    assert entry.confidence_reason == "All fields present."
    assert entry.proposed_route == "create_developer_summary"
    assert entry.final_route == "create_developer_summary"
    assert entry.router_reason == "Actionable report."
    assert entry.requires_human is False
    assert entry.risky_action is False
    assert entry.red_flags == []
    assert entry.missing_info == []
    assert entry.human_decision is None
    assert entry.report_id != ""
    assert "T" in entry.timestamp


def test_report_id_is_stable():
    pre = _make_preprocessed(sanitized_text="same text")
    e1 = build_audit_entry(
        input_source="a",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=pre,
    )
    e2 = build_audit_entry(
        input_source="b",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=pre,
    )
    assert e1.report_id == e2.report_id  # same text → same hash


def test_no_raw_email_logged(tmp_path: Path):
    # Email is masked by preprocess; audit log should not contain the real address.
    pre = _make_preprocessed(sanitized_text="User [EMAIL] reported a crash.", extracted_email="user@example.com")
    log_file = tmp_path / "audit.jsonl"
    entry = build_audit_entry(
        input_source="stdin",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=pre,
    )
    append_audit_entry(entry, log_path=log_file)
    raw = log_file.read_text(encoding="utf-8")
    assert "user@example.com" not in raw


def test_build_audit_entry_with_human_decision():
    entry = build_audit_entry(
        input_source="stdin",
        classification=_make_classification(category="spam", route="needs_human_approval_to_close"),
        decision=_make_decision(route="needs_human_approval_to_close", requires_human=True, risky_action=True),
        preprocessed=_make_preprocessed(),
        human_decision=True,
    )
    assert entry.human_decision is True
    assert entry.final_route == "needs_human_approval_to_close"


def test_build_audit_entry_with_red_flags():
    entry = build_audit_entry(
        input_source="report.txt",
        classification=_make_classification(category="security", urgency="critical"),
        decision=_make_decision(route="escalate_to_human", requires_human=True),
        preprocessed=_make_preprocessed(red_flags_triggered=["RF001", "RF004"]),
    )
    assert entry.red_flags == ["RF001", "RF004"]


def test_build_audit_entry_includes_proposed_and_final_route():
    # Classifier proposed create_developer_summary but router overrode to low_confidence_review.
    entry = build_audit_entry(
        input_source="test.txt",
        classification=_make_classification(route="create_developer_summary"),
        decision=_make_decision(route="low_confidence_review", requires_human=True),
        preprocessed=_make_preprocessed(),
    )
    assert entry.proposed_route == "create_developer_summary"
    assert entry.final_route == "low_confidence_review"


def test_append_and_read_back(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    entry = build_audit_entry(
        input_source="test.txt",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=_make_preprocessed(),
    )
    append_audit_entry(entry, log_path=log_file)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["input_source"] == "test.txt"
    assert parsed["category"] == "bug"
    assert parsed["human_decision"] is None
    assert "report_id" in parsed
    assert "confidence_reason" in parsed


def test_append_creates_parent_directories(tmp_path: Path):
    log_file = tmp_path / "outputs" / "nested" / "audit.jsonl"
    entry = build_audit_entry(
        input_source="test.txt",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=_make_preprocessed(),
    )
    append_audit_entry(entry, log_path=log_file)
    assert log_file.exists()


def test_append_multiple_entries(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    for i in range(3):
        entry = build_audit_entry(
            input_source=f"report_{i}.txt",
            classification=_make_classification(),
            decision=_make_decision(),
            preprocessed=_make_preprocessed(),
        )
        append_audit_entry(entry, log_path=log_file)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    sources = [json.loads(line)["input_source"] for line in lines]
    assert sources == ["report_0.txt", "report_1.txt", "report_2.txt"]
