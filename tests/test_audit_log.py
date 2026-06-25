"""Tests for the JSONL audit log (audit_log.py)."""

import json
from pathlib import Path

import pytest

from bug_triage.audit_log import AuditEntry, append_audit_entry, build_audit_entry
from bug_triage.models import BugClassification, PreprocessedBugReport, RouteDecision


def _make_classification(**overrides) -> BugClassification:
    defaults = dict(
        category="bug",
        urgency="medium",
        sentiment="calm",
        confidence="high",
        missing_info=[],
        route="create_developer_summary",
        reasoning="Complete report.",
    )
    defaults.update(overrides)
    return BugClassification(**defaults)


def _make_preprocessed(**overrides) -> PreprocessedBugReport:
    defaults = dict(original_text="hello", sanitized_text="hello")
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
        source="samples/complete_bug.txt",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=_make_preprocessed(),
    )
    assert entry.source == "samples/complete_bug.txt"
    assert entry.category == "bug"
    assert entry.urgency == "medium"
    assert entry.confidence == "high"
    assert entry.route == "create_developer_summary"
    assert entry.requires_human is False
    assert entry.risky_action is False
    assert entry.red_flags_triggered == []
    assert entry.missing_info == []
    assert entry.human_decision is None
    assert "T" in entry.timestamp


def test_build_audit_entry_with_human_decision():
    entry = build_audit_entry(
        source="stdin",
        classification=_make_classification(category="spam", route="needs_human_approval_to_close"),
        decision=_make_decision(route="needs_human_approval_to_close", requires_human=True, risky_action=True),
        preprocessed=_make_preprocessed(),
        human_decision=True,
    )
    assert entry.human_decision is True
    assert entry.route == "needs_human_approval_to_close"


def test_build_audit_entry_with_red_flags():
    entry = build_audit_entry(
        source="report.txt",
        classification=_make_classification(category="security", urgency="critical"),
        decision=_make_decision(route="escalate_to_human", requires_human=True),
        preprocessed=_make_preprocessed(red_flags_triggered=["RF001", "RF004"]),
    )
    assert entry.red_flags_triggered == ["RF001", "RF004"]


def test_append_and_read_back(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    entry = build_audit_entry(
        source="test.txt",
        classification=_make_classification(),
        decision=_make_decision(),
        preprocessed=_make_preprocessed(),
    )
    append_audit_entry(entry, log_path=log_file)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "test.txt"
    assert parsed["category"] == "bug"
    assert parsed["human_decision"] is None


def test_append_multiple_entries(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    for i in range(3):
        entry = build_audit_entry(
            source=f"report_{i}.txt",
            classification=_make_classification(),
            decision=_make_decision(),
            preprocessed=_make_preprocessed(),
        )
        append_audit_entry(entry, log_path=log_file)

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    sources = [json.loads(line)["source"] for line in lines]
    assert sources == ["report_0.txt", "report_1.txt", "report_2.txt"]


def test_audit_entry_is_valid_json(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"
    entry = build_audit_entry(
        source="test.txt",
        classification=_make_classification(missing_info=["version", "os"]),
        decision=_make_decision(route="ask_for_missing_info"),
        preprocessed=_make_preprocessed(),
    )
    append_audit_entry(entry, log_path=log_file)
    raw = log_file.read_text(encoding="utf-8").strip()
    parsed = json.loads(raw)
    assert parsed["missing_info"] == ["version", "os"]
    assert parsed["route"] == "ask_for_missing_info"
