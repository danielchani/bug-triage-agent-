"""Tests for the expanded input surface: stdin, batch folder, CSV (main.py)."""

import asyncio
import os
from io import StringIO
from pathlib import Path

import pytest

from bug_triage.main import _read_csv_reports, run_batch, run_csv, run_report


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("BUG_TRIAGE_MOCK_LLM", "true")


# ── CSV parsing ───────────────────────────────────────────────────────────────

def test_read_csv_reports_text_column(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text("text,extra\nhello world,foo\napp crashes,bar\n", encoding="utf-8")
    result = _read_csv_reports(csv_file)
    assert len(result) == 2
    assert result[0] == ("hello world", "reports.csv:row1")
    assert result[1] == ("app crashes", "reports.csv:row2")


def test_read_csv_reports_body_column(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text("body\nsome text\n", encoding="utf-8")
    result = _read_csv_reports(csv_file)
    assert result[0][0] == "some text"


def test_read_csv_reports_with_id_column(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text("id,text\nBUG-001,crash on login\n", encoding="utf-8")
    result = _read_csv_reports(csv_file)
    assert result[0] == ("crash on login", "BUG-001")


def test_read_csv_reports_skips_empty_rows(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text("text\nhello\n   \nworld\n", encoding="utf-8")
    result = _read_csv_reports(csv_file)
    assert len(result) == 2


def test_read_csv_reports_raises_on_missing_column(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text("title,summary\nhello,world\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must have one of these columns"):
        _read_csv_reports(csv_file)


# ── stdin run ─────────────────────────────────────────────────────────────────

def test_run_report_stdin_does_not_raise():
    raw_text = (
        "Export to CSV fails on rows with commas.\n"
        "Steps to reproduce: add a record with a comma in Notes, then export.\n"
        "Expected: the row is quoted correctly.\n"
        "Actual: the export raises an error.\n"
        "Environment: Web app v4.12.1, Windows 11.\n"
    )
    asyncio.run(run_report(raw_text, "stdin", auto_approve=None, no_audit=True))


# ── batch folder run ──────────────────────────────────────────────────────────

def test_run_batch_processes_all_txt_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text(
        "Export to CSV fails.\nSteps to reproduce: click Export.\n"
        "Expected: file downloads. Actual: page crashes.\nVersion: v2.0.0. OS: Windows 11.\n",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text(
        "Export to CSV fails.\nSteps to reproduce: click Export.\n"
        "Expected: file downloads. Actual: page crashes.\nVersion: v2.0.0. OS: Windows 11.\n",
        encoding="utf-8",
    )
    asyncio.run(run_batch(tmp_path, auto_approve=None, no_audit=True))


def test_run_batch_empty_folder_does_not_raise(tmp_path: Path):
    asyncio.run(run_batch(tmp_path, auto_approve=None, no_audit=True))


# ── CSV run ───────────────────────────────────────────────────────────────────

def test_run_csv_processes_reports(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text(
        "text\n"
        "Export to CSV fails. Steps to reproduce: click Export. "
        "Expected: file downloads. Actual: crash. Version v2.0.0. OS: Windows 11.\n",
        encoding="utf-8",
    )
    asyncio.run(run_csv(csv_file, auto_approve=None, no_audit=True))
