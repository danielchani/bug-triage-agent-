"""Plain-function preprocess step: normalizes a raw bug report and extracts a
few simple structured signals (email, issue id, version, OS, stack trace)
before it's handed to the classifier agent.

This module is deterministic and has no LLM/network dependency, per AGENTS.md.
"""

import re

from agent_framework import WorkflowContext, executor

from bug_triage.models import BugReportInput, PreprocessedBugReport
from bug_triage.red_flags import evaluate_red_flags

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_ISSUE_ID_RE = re.compile(r"#\d+|\b[A-Z]{2,}-\d+\b")
_VERSION_RE = re.compile(r"\bv(\d+(?:\.\d+){1,2})\b|\bversion\s+(\d+(?:\.\d+){1,2})\b", re.IGNORECASE)

# Checked in order so that "macOS"/"iOS" are matched before any generic "OS" text.
_OS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmacOS\b", re.IGNORECASE), "macOS"),
    (re.compile(r"\biOS\b", re.IGNORECASE), "iOS"),
    (re.compile(r"\bAndroid\b", re.IGNORECASE), "Android"),
    (re.compile(r"\bWindows\b", re.IGNORECASE), "Windows"),
    (re.compile(r"\bLinux\b", re.IGNORECASE), "Linux"),
]

_STACK_TRACE_RE = re.compile(
    r"traceback \(most recent call last\)|stack ?trace|File \"[^\"]+\", line \d+|^\s*at \S+\(",
    re.IGNORECASE | re.MULTILINE,
)


def preprocess(report: BugReportInput) -> PreprocessedBugReport:
    """Pure function: extract structured signals and mask PII in the raw text."""
    text = report.raw_text

    email_match = _EMAIL_RE.search(text)
    extracted_email = email_match.group(0) if email_match else None
    sanitized_text = _EMAIL_RE.sub("[EMAIL]", text)

    issue_match = _ISSUE_ID_RE.search(text)
    extracted_issue_id = issue_match.group(0) if issue_match else None

    extracted_version = None
    version_match = _VERSION_RE.search(text)
    if version_match:
        extracted_version = version_match.group(1) or version_match.group(2)

    extracted_os = None
    for pattern, canonical_name in _OS_PATTERNS:
        if pattern.search(text):
            extracted_os = canonical_name
            break

    has_stack_trace = bool(_STACK_TRACE_RE.search(text))

    rf_result = evaluate_red_flags(sanitized_text)

    return PreprocessedBugReport(
        original_text=text,
        sanitized_text=sanitized_text,
        extracted_email=extracted_email,
        extracted_issue_id=extracted_issue_id,
        extracted_version=extracted_version,
        extracted_os=extracted_os,
        has_stack_trace=has_stack_trace,
        red_flags_triggered=rf_result.flags,
        red_flags_reason=rf_result.reason,
    )


@executor(id="preprocess")
async def preprocess_executor(report: BugReportInput, ctx: WorkflowContext[PreprocessedBugReport]) -> None:
    """Workflow entry point: runs `preprocess` and forwards the result to the classifier."""
    await ctx.send_message(preprocess(report))
