"""Routing logic: turns a BugClassification into a deterministic RouteDecision.

The classifier proposes its own best-guess `route` on `BugClassification`, but
the workflow's switch-case routing is driven entirely by this pure,
fully-unit-tested function - it is the final routing authority, per AGENTS.md.

Priority order (first match wins):
  0. red_flags_triggered is non-empty               -> escalate_to_human  (hard override)
  1. category == "security" or urgency == "critical" -> escalate_to_human
  2. confidence < LOW_CONFIDENCE_THRESHOLD (0.60)   -> low_confidence_review
  3. missing_info is non-empty                       -> ask_for_missing_info
  4. category in {duplicate, spam, invalid}          -> needs_human_approval_to_close
  5. otherwise                                       -> create_developer_summary

This module has no LLM/network dependency.
"""

from __future__ import annotations

from agent_framework import WorkflowContext, executor

from bug_triage.models import BugClassification, ClassifiedBugReport, PreprocessedBugReport, RouteDecision, RoutedBugReport

_NOT_A_BUG_CATEGORIES = {"duplicate", "spam", "invalid"}

# Reports with confidence below this threshold are routed to low_confidence_review
# rather than any automated action. Keep this in sync with classifier_agent.py.
LOW_CONFIDENCE_THRESHOLD = 0.60


def decide_route(
    classification: BugClassification,
    preprocessed: PreprocessedBugReport | None = None,
) -> RouteDecision:
    if preprocessed is not None and preprocessed.red_flags_triggered:
        reason = preprocessed.red_flags_reason or f"Rules triggered: {', '.join(preprocessed.red_flags_triggered)}."
        return RouteDecision(
            route="escalate_to_human",
            requires_human=True,
            risky_action=False,
            explanation=reason,
        )

    if classification.category == "security" or classification.urgency == "critical":
        return RouteDecision(
            route="escalate_to_human",
            requires_human=True,
            risky_action=False,
            explanation="Security-related or critical-urgency reports are escalated directly to a human.",
        )

    if classification.confidence < LOW_CONFIDENCE_THRESHOLD:
        return RouteDecision(
            route="low_confidence_review",
            requires_human=True,
            risky_action=False,
            explanation=(
                f"Classifier confidence {classification.confidence:.0%} is below the "
                f"{LOW_CONFIDENCE_THRESHOLD:.0%} threshold. {classification.confidence_reason}"
            ),
        )

    if classification.missing_info:
        missing = ", ".join(classification.missing_info)
        return RouteDecision(
            route="ask_for_missing_info",
            requires_human=False,
            risky_action=False,
            explanation=f"Report is missing: {missing}.",
        )

    if classification.category in _NOT_A_BUG_CATEGORIES:
        return RouteDecision(
            route="needs_human_approval_to_close",
            requires_human=True,
            risky_action=True,
            explanation=(
                f"Category '{classification.category}' suggests closing/rejecting this report, "
                "which requires human approval before acting."
            ),
        )

    return RouteDecision(
        route="create_developer_summary",
        requires_human=False,
        risky_action=False,
        explanation="Looks like a complete, actionable bug report.",
    )


@executor(id="router")
async def router_executor(report: ClassifiedBugReport, ctx: WorkflowContext[RoutedBugReport]) -> None:
    """Computes the final route and forwards a RoutedBugReport to the switch-case edges."""
    decision = decide_route(report.classification, report.preprocessed)
    await ctx.send_message(
        RoutedBugReport(
            preprocessed=report.preprocessed,
            classification=report.classification,
            decision=decision,
        )
    )
