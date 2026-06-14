"""Tests that the workflow graph builds correctly and runs end-to-end.

These force BUG_TRIAGE_MOCK_LLM=true so they're fully offline - no network
access or API key required. Async runs are driven with asyncio.run() so no
extra pytest plugin is needed.
"""

import asyncio

import pytest

from bug_triage.models import BugReportInput
from bug_triage.workflow import build_workflow


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("BUG_TRIAGE_MOCK_LLM", "true")


def test_build_workflow_wires_expected_executors():
    workflow = build_workflow()
    assert workflow.start_executor_id == "preprocess"
    assert set(workflow.executors) == {
        "preprocess",
        "classifier",
        "router",
        "escalate_to_human",
        "ask_for_missing_info",
        "create_developer_summary",
        "needs_human_approval_to_close",
    }


async def _run_until_idle(workflow, raw_text):
    report = BugReportInput(raw_text=raw_text)
    outputs: list[str] = []
    pending_request_id = None

    async for event in workflow.run(report, stream=True):
        if event.type == "output":
            outputs.append(event.data)
        elif event.type == "request_info":
            pending_request_id = event.request_id

    return outputs, pending_request_id


def test_security_report_escalates_to_human():
    workflow = build_workflow()
    outputs, pending_request_id = asyncio.run(
        _run_until_idle(workflow, "There is an authentication bypass vulnerability in the login flow.")
    )
    assert pending_request_id is None
    assert any("ESCALATED TO HUMAN" in output for output in outputs)


def test_vague_report_asks_for_missing_info():
    workflow = build_workflow()
    outputs, pending_request_id = asyncio.run(
        _run_until_idle(workflow, "The app crashes sometimes, it's really annoying, please fix ASAP.")
    )
    assert pending_request_id is None
    assert any("MORE INFO NEEDED" in output for output in outputs)


def test_complete_bug_report_creates_developer_summary():
    workflow = build_workflow()
    raw_text = (
        "Export to CSV fails on rows with commas.\n"
        "Steps to reproduce: add a record with a comma in Notes, then export.\n"
        "Expected: the row is quoted correctly.\n"
        "Actual: the export raises an error.\n"
        "Environment: Web app v4.12.1, Windows 11.\n"
    )
    outputs, pending_request_id = asyncio.run(_run_until_idle(workflow, raw_text))
    assert pending_request_id is None
    assert any("DEVELOPER TICKET SUMMARY" in output for output in outputs)


async def _run_and_resume(workflow, raw_text, *, approved):
    outputs, pending_request_id = await _run_until_idle(workflow, raw_text)
    assert pending_request_id is not None
    assert outputs == []

    resumed_outputs: list[str] = []
    async for event in workflow.run(stream=True, responses={pending_request_id: approved}):
        if event.type == "output":
            resumed_outputs.append(event.data)
    return resumed_outputs


def test_duplicate_report_pauses_for_approval_then_closes_on_approval():
    workflow = build_workflow()
    raw_text = "This is the same as ticket #4821, already reported last month."

    resumed_outputs = asyncio.run(_run_and_resume(workflow, raw_text, approved=True))
    assert any("closed/rejected" in output for output in resumed_outputs)


def test_duplicate_report_escalates_on_rejection():
    workflow = build_workflow()
    raw_text = "This is the same as ticket #4821, already reported last month."

    resumed_outputs = asyncio.run(_run_and_resume(workflow, raw_text, approved=False))
    assert any("escalated_to_human_review" in output for output in resumed_outputs)
