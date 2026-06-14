"""Routing logic: turns a BugClassification into a deterministic RouteDecision.

The classifier proposes its own best-guess `route` on `BugClassification`, but
the workflow's switch-case routing is driven entirely by this pure,
fully-unit-tested function - it is the final routing authority, per AGENTS.md.

Priority order (first match wins):
  1. category == "security" or urgency == "critical"  -> escalate_to_human
  2. missing_info is non-empty                        -> ask_for_missing_info
  3. category in {duplicate, spam, invalid}           -> needs_human_approval_to_close
  4. otherwise                                        -> create_developer_summary

This module has no LLM/network dependency.
"""

from agent_framework import WorkflowContext, executor

from bug_triage.models import BugClassification, ClassifiedBugReport, RouteDecision, RoutedBugReport

_NOT_A_BUG_CATEGORIES = {"duplicate", "spam", "invalid"}


def decide_route(classification: BugClassification) -> RouteDecision:
    if classification.category == "security" or classification.urgency == "critical":
        return RouteDecision(
            route="escalate_to_human",
            requires_human=True,
            risky_action=False,
            explanation="Security-related or critical-urgency reports are escalated directly to a human.",
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
    decision = decide_route(report.classification)
    await ctx.send_message(
        RoutedBugReport(
            preprocessed=report.preprocessed,
            classification=report.classification,
            decision=decision,
        )
    )
