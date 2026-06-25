"""JSONL decision audit log.

Every triage run can append one line to a JSONL file.
Use --audit-log <path> on the CLI, or set TRIAGE_AUDIT_LOG env var.

Format: one JSON object per line (JSONL), fields defined by AuditEntry.
No raw PII is logged; email addresses are already masked by preprocess.py.
"""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from bug_triage.models import BugClassification, PreprocessedBugReport, RouteDecision

_DEFAULT_LOG_PATH = Path("triage_audit.jsonl")


def _default_log_path() -> Path:
    env = os.environ.get("TRIAGE_AUDIT_LOG", "").strip()
    return Path(env) if env else _DEFAULT_LOG_PATH


def _report_id(sanitized_text: str) -> str:
    """Stable 12-character hex hash of the sanitized report text."""
    return hashlib.sha256(sanitized_text.encode()).hexdigest()[:12]


class AuditEntry(BaseModel):
    timestamp: str
    report_id: str
    input_source: str
    category: str
    urgency: str
    sentiment: str
    confidence: float
    confidence_reason: str
    proposed_route: str
    final_route: str
    router_reason: str
    requires_human: bool
    risky_action: bool
    red_flags: list[str]
    missing_info: list[str]
    reasoning: str
    human_decision: bool | None = None
    action_status: str = "completed"


def build_audit_entry(
    *,
    input_source: str,
    classification: BugClassification,
    decision: RouteDecision,
    preprocessed: PreprocessedBugReport,
    human_decision: bool | None = None,
    action_status: str = "completed",
) -> AuditEntry:
    return AuditEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        report_id=_report_id(preprocessed.sanitized_text),
        input_source=input_source,
        category=classification.category,
        urgency=classification.urgency,
        sentiment=classification.sentiment,
        confidence=classification.confidence,
        confidence_reason=classification.confidence_reason,
        proposed_route=classification.route,
        final_route=decision.route,
        router_reason=decision.explanation,
        requires_human=decision.requires_human,
        risky_action=decision.risky_action,
        red_flags=preprocessed.red_flags_triggered,
        missing_info=classification.missing_info,
        reasoning=classification.reasoning,
        human_decision=human_decision,
        action_status=action_status,
    )


def append_audit_entry(entry: AuditEntry, log_path: Path | None = None) -> None:
    path = log_path if log_path is not None else _default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")
