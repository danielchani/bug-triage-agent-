"""CLI entrypoint for running a single bug report through the triage workflow.

Usage:
    python -m bug_triage.main samples/<file>.txt [--auto-approve | --auto-reject]

Streamed event tags (WorkflowEvent.type -> printed prefix):
    executor_invoked   -> [executor_started]
    executor_completed -> [executor_completed]
                           (the router executor additionally prints a [route]
                           block with the final RouteDecision)
    request_info       -> [request_info]   bonus human-approval pause, see actions.py
    output             -> [output]          final yielded result of the run
"""

import argparse
import asyncio
import sys
from pathlib import Path

from bug_triage.models import BugReportInput
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


async def run_file(path: Path, auto_approve: bool | None) -> None:
    workflow = build_workflow()
    report = BugReportInput(raw_text=path.read_text(encoding="utf-8"), source=str(path))

    stream = workflow.run(report, stream=True)
    while True:
        pending_request_id: str | None = None

        async for event in stream:
            _print_event(event)
            if event.type == "request_info":
                pending_request_id = event.request_id

        if pending_request_id is None:
            break

        # Resume the same workflow run, feeding the human's decision back to the
        # NeedsHumanApprovalExecutor's @response_handler (see actions.py).
        approved = _ask_for_approval(auto_approve)
        stream = workflow.run(stream=True, responses={pending_request_id: approved})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bug report through the triage workflow.")
    parser.add_argument("report_path", type=Path, help="Path to a raw bug report .txt file (e.g. samples/foo.txt)")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--auto-approve", action="store_true", help="Automatically approve any human-approval request."
    )
    group.add_argument(
        "--auto-reject", action="store_true", help="Automatically reject any human-approval request."
    )

    args = parser.parse_args(argv)

    auto_approve: bool | None = None
    if args.auto_approve:
        auto_approve = True
    elif args.auto_reject:
        auto_approve = False

    asyncio.run(run_file(args.report_path, auto_approve))
    return 0


if __name__ == "__main__":
    sys.exit(main())
