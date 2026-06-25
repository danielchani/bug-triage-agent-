"""CLI entrypoint for running bug reports through the triage workflow.

Usage:
    python -m bug_triage.main samples/<file>.txt        # single file
    python -m bug_triage.main --stdin                   # read from stdin
    python -m bug_triage.main --batch samples/          # all .txt files in folder
    python -m bug_triage.main --csv reports.csv         # CSV with a "text" column
    python -m bug_triage.main samples/foo.txt --audit-log outputs/audit.jsonl

Streamed event tags (WorkflowEvent.type -> printed prefix):
    executor_invoked   -> [executor_started]
    executor_completed -> [executor_completed]
                          (router additionally prints a [route] block)
    request_info       -> [request_info]  human-approval pause (see actions.py)
    output             -> [output]        final result of the run
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from bug_triage.audit_log import append_audit_entry, build_audit_entry
from bug_triage.models import BugReportInput, RoutedBugReport
from bug_triage.workflow import build_workflow


def _print_event(event: object) -> None:
    event_type = getattr(event, "type", None)

    if event_type == "executor_invoked":
        print(f"[executor_started] {event.executor_id}")  # type: ignore[attr-defined]

    elif event_type == "executor_completed":
        print(f"[executor_completed] {event.executor_id}")  # type: ignore[attr-defined]
        if event.executor_id == "router" and event.data:  # type: ignore[attr-defined]
            decision = event.data[0].decision  # type: ignore[attr-defined]
            print(f"[route] -> {decision.route}")
            print(f"[route] requires_human={decision.requires_human} risky_action={decision.risky_action}")
            print(f"[route] {decision.explanation}")

    elif event_type == "request_info":
        request = event.data  # type: ignore[attr-defined]
        print(f"[request_info] {event.source_executor_id} is requesting human approval:")  # type: ignore[attr-defined]
        print(f"  summary: {request.summary}")
        print(f"  category: {request.category}")
        print(f"  proposed_action: {request.proposed_action}")
        print(f"  reasoning: {request.reasoning}")

    elif event_type == "output":
        print(f"[output] {event.executor_id}:")  # type: ignore[attr-defined]
        print(event.data)  # type: ignore[attr-defined]


def _ask_for_approval(auto_approve: bool | None) -> bool:
    if auto_approve is not None:
        return auto_approve
    while True:
        reply = input("Approve this action? [y/n]: ").strip().lower()
        if reply in {"y", "yes"}:
            return True
        if reply in {"n", "no"}:
            return False


async def run_report(
    raw_text: str,
    source: str,
    auto_approve: bool | None,
    *,
    audit_log: Path | None = None,
) -> None:
    if not raw_text.strip():
        print(f"[error] Empty input from {source!r} — skipping.", file=sys.stderr)
        return

    workflow = build_workflow()
    report = BugReportInput(raw_text=raw_text, source=source)

    stream = workflow.run(report, stream=True)
    routed_report: RoutedBugReport | None = None
    human_decision: bool | None = None

    while True:
        pending_request_id: str | None = None

        async for event in stream:
            _print_event(event)
            if event.type == "request_info":
                pending_request_id = event.request_id
            elif event.type == "executor_completed" and event.executor_id == "router" and event.data:
                routed_report = event.data[0]

        if pending_request_id is None:
            break

        human_decision = _ask_for_approval(auto_approve)
        stream = workflow.run(stream=True, responses={pending_request_id: human_decision})

    if audit_log is not None and routed_report is not None:
        entry = build_audit_entry(
            input_source=source,
            classification=routed_report.classification,
            decision=routed_report.decision,
            preprocessed=routed_report.preprocessed,
            human_decision=human_decision,
        )
        append_audit_entry(entry, log_path=audit_log)


def _read_csv_reports(csv_path: Path) -> list[tuple[str, str]]:
    """Return list of (raw_text, source) pairs from a CSV file.

    Accepts column names: text, body, description, report (first match wins).
    """
    text_columns = ("text", "body", "description", "report")
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file {csv_path} has no header row.")
        col = next((c for c in text_columns if c in reader.fieldnames), None)
        if col is None:
            raise ValueError(
                f"CSV {csv_path} must have one of these columns: {', '.join(text_columns)}. "
                f"Found: {', '.join(reader.fieldnames)}"
            )
        id_col = next((c for c in ("id", "source", "name") if c in (reader.fieldnames or [])), None)
        rows = list(reader)

    results: list[tuple[str, str]] = []
    for i, row in enumerate(rows):
        text = row[col].strip()
        source = row[id_col].strip() if id_col and row.get(id_col) else f"{csv_path.name}:row{i + 1}"
        if text:
            results.append((text, source))
    return results


async def run_file(
    path: Path, auto_approve: bool | None, *, audit_log: Path | None = None
) -> None:
    raw_text = path.read_text(encoding="utf-8")
    await run_report(raw_text, str(path), auto_approve, audit_log=audit_log)


async def run_batch(
    folder: Path, auto_approve: bool | None, *, audit_log: Path | None = None
) -> None:
    txt_files = sorted(folder.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {folder}")
        return
    for i, path in enumerate(txt_files):
        if i > 0:
            print("\n" + "─" * 60)
        print(f"\n[batch] Processing: {path.name}")
        try:
            await run_file(path, auto_approve, audit_log=audit_log)
        except Exception as exc:  # noqa: BLE001
            print(f"[batch] ERROR processing {path.name}: {exc}", file=sys.stderr)


async def run_csv(
    csv_path: Path, auto_approve: bool | None, *, audit_log: Path | None = None
) -> None:
    reports = _read_csv_reports(csv_path)
    if not reports:
        print(f"No non-empty rows found in {csv_path}")
        return
    for i, (raw_text, source) in enumerate(reports):
        if i > 0:
            print("\n" + "─" * 60)
        print(f"\n[csv] Processing: {source}")
        await run_report(raw_text, source, auto_approve, audit_log=audit_log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bug reports through the triage workflow.")

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "report_path",
        nargs="?",
        type=Path,
        help="Path to a raw bug report .txt file.",
    )
    input_group.add_argument("--stdin", action="store_true", help="Read report text from standard input.")
    input_group.add_argument("--batch", type=Path, metavar="FOLDER", help="Triage all .txt files in FOLDER.")
    input_group.add_argument("--csv", type=Path, metavar="FILE", help="Triage reports from a CSV file (needs a 'text' column).")

    approval_group = parser.add_mutually_exclusive_group()
    approval_group.add_argument("--auto-approve", action="store_true", help="Automatically approve any human-approval request.")
    approval_group.add_argument("--auto-reject", action="store_true", help="Automatically reject any human-approval request.")

    parser.add_argument(
        "--audit-log",
        type=Path,
        metavar="FILE",
        help="Append JSONL audit entries to FILE (parent directories are created if needed).",
    )

    args = parser.parse_args(argv)

    auto_approve: bool | None = None
    if args.auto_approve:
        auto_approve = True
    elif args.auto_reject:
        auto_approve = False

    audit_log: Path | None = args.audit_log

    if args.batch:
        asyncio.run(run_batch(args.batch, auto_approve, audit_log=audit_log))
    elif args.csv:
        asyncio.run(run_csv(args.csv, auto_approve, audit_log=audit_log))
    elif args.stdin:
        raw_text = sys.stdin.read()
        asyncio.run(run_report(raw_text, "stdin", auto_approve, audit_log=audit_log))
    elif args.report_path is not None:
        asyncio.run(run_file(args.report_path, auto_approve, audit_log=audit_log))
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
