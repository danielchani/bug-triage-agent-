"""Pydantic models shared across the bug-triage workflow."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

BugCategory = Literal[
    "bug", "security", "performance", "feature_request", "duplicate", "spam", "invalid", "other"
]
UrgencyLevel = Literal["low", "medium", "high", "critical"]
SentimentLevel = Literal["calm", "frustrated", "angry"]
ConfidenceLevel = Literal["low", "medium", "high"]
RouteName = Literal[
    "escalate_to_human", "ask_for_missing_info", "create_developer_summary", "needs_human_approval_to_close"
]


class BugReportInput(BaseModel):
    """Raw bug report as submitted (e.g. the contents of a sample .txt file)."""

    raw_text: str
    source: str | None = None
    received_at: str | None = None


class PreprocessedBugReport(BaseModel):
    """Output of the deterministic preprocess step."""

    original_text: str
    sanitized_text: str
    extracted_email: str | None = None
    extracted_issue_id: str | None = None
    extracted_version: str | None = None
    extracted_os: str | None = None
    has_stack_trace: bool = False
    red_flags_triggered: list[str] = Field(default_factory=list)


class BugClassification(BaseModel):
    """Required structured output produced by the classifier agent."""

    category: BugCategory
    urgency: UrgencyLevel
    sentiment: SentimentLevel
    confidence: ConfidenceLevel
    missing_info: list[str] = Field(default_factory=list)
    route: RouteName
    reasoning: str


class RouteDecision(BaseModel):
    """Final, deterministic routing decision computed by router.py.

    `route` here is the system-enforced route - it may differ from
    `BugClassification.route`, which is only the classifier's own proposal.
    """

    route: RouteName
    requires_human: bool
    risky_action: bool
    explanation: str


class ClassifiedBugReport(BaseModel):
    """Bundle passed from the classifier executor to the router executor."""

    preprocessed: PreprocessedBugReport
    classification: BugClassification


class RoutedBugReport(BaseModel):
    """Bundle passed from the router executor to the action executors."""

    preprocessed: PreprocessedBugReport
    classification: BugClassification
    decision: RouteDecision


@dataclass
class ApprovalRequest:
    """Payload sent to the human via `request_info` for the approval gate."""

    summary: str
    category: BugCategory
    proposed_action: str
    reasoning: str
