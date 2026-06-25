"""Tests for the expanded input surface: --stdin, --batch, --csv (main.py)."""

import asyncio
from pathlib import Path

import pytest

from bug_triage.main import _read_csv_reports, run_batch, run_csv, run_report


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("BUG_TRIAGE_MOCK_LLM", "true")


_COMPLETE_REPORT = (
    "Export to CSV fails on rows with commas.\n"
    "Steps to reproduce: add a record with a comma in Notes, then export.\n"
    "Expected: the row is quoted correctly.\n"
    "Actual: the export raises an error.\n"
    "Environment: Web app v4.12.1, Windows 11.\n"
)


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
    asyncio.run(run_report(_COMPLETE_REPORT, "stdin", auto_approve=None))


def test_run_report_empty_input_does_not_raise():
    asyncio.run(run_report("   ", "stdin", auto_approve=None))


# ── batch folder run ──────────────────────────────────────────────────────────

def test_run_batch_processes_all_txt_files(tmp_path: Path):
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(_COMPLETE_REPORT, encoding="utf-8")
    asyncio.run(run_batch(tmp_path, auto_approve=None))


def test_run_batch_empty_folder_does_not_raise(tmp_path: Path):
    asyncio.run(run_batch(tmp_path, auto_approve=None))


def test_run_batch_continues_on_failure(tmp_path: Path, capsys):
    # First file is valid; second file will fail (we make it a directory to force a read error).
    (tmp_path / "a.txt").write_text(_COMPLETE_REPORT, encoding="utf-8")
    bad = tmp_path / "b.txt"
    bad.mkdir()  # creates a directory with .txt name — reading it raises IsADirectoryError
    asyncio.run(run_batch(tmp_path, auto_approve=None))
    stderr = capsys.readouterr().err
    assert "ERROR" in stderr  # error reported but run didn't abort


def test_run_batch_writes_audit_log(tmp_path: Path):
    (tmp_path / "report.txt").write_text(_COMPLETE_REPORT, encoding="utf-8")
    log = tmp_path / "audit.jsonl"
    asyncio.run(run_batch(tmp_path, auto_approve=None, audit_log=log))
    assert log.exists()
    assert log.stat().st_size > 0


# ── CSV run ───────────────────────────────────────────────────────────────────

def test_run_csv_processes_reports(tmp_path: Path):
    csv_file = tmp_path / "reports.csv"
    csv_file.write_text(f"text\n{_COMPLETE_REPORT}\n", encoding="utf-8")
    asyncio.run(run_csv(csv_file, auto_approve=None))
