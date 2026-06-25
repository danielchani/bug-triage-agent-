"""JSONL decision audit log.

Every triage run appends one line to `triage_audit.jsonl` (or a path set via
the TRIAGE_AUDIT_LOG env var). The log is never read by the workflow itself —
it exists purely for observability, debugging, and human review.

Format: one JSON object per line (JSONL), fields defined by AuditEntry.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from bug_triage.models import BugClassification, PreprocessedBugReport, RouteDecision

_DEFAULT_LOG_PATH = Path("triage_audit.jsonl")


def _default_log_path() -> Path:
    env = os.environ.get("TRIAGE_AUDIT_LOG", "").strip()
    return Path(env) if env else _DEFAULT_LOG_PATH


class AuditEntry(BaseModel):
    timestamp: str
    source: str
    category: str
    urgency: str
    confidence: str
    route: str
    requires_human: bool
    risky_action: bool
    red_flags_triggered: list[str]
    missing_info: list[str]
    reasoning: str
    human_decision: bool | None = None


def build_audit_entry(
    *,
    source: str,
    classification: BugClassification,
    decision: RouteDecision,
    preprocessed: PreprocessedBugReport,
    human_decision: bool | None = None,
) -> AuditEntry:
    return AuditEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
        category=classification.category,
        urgency=classification.urgency,
        confidence=classification.confidence,
        route=decision.route,
        requires_human=decision.requires_human,
        risky_action=decision.risky_action,
        red_flags_triggered=preprocessed.red_flags_triggered,
        missing_info=classification.missing_info,
        reasoning=classification.reasoning,
        human_decision=human_decision,
    )


def append_audit_entry(entry: AuditEntry, log_path: Path | None = None) -> None:
    path = log_path if log_path is not None else _default_log_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")
