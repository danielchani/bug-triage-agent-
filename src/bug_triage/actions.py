"""Terminal action executors - one per RouteDecision.route.

`needs_human_approval_to_close` is the bonus human-in-the-loop gate: before the
workflow closes/rejects an invalid, spam, or duplicate report, it pauses with
`ctx.request_info(...)` and waits for a human y/n response. This is the
current MAF request-response API; we deliberately avoid the older
`RequestInfoExecutor` pattern.
"""

from agent_framework import Executor, WorkflowContext, executor, handler, response_handler

from bug_triage.models import ApprovalRequest, RoutedBugReport


@executor(id="low_confidence_review")
async def low_confidence_review_executor(report: RoutedBugReport, ctx: WorkflowContext[None, str]) -> None:
    """Human-review summary for reports the classifier wasn't confident about."""
    c = report.classification
    output = (
        "LOW CONFIDENCE — HUMAN REVIEW NEEDED\n"
        f"Confidence: {c.confidence:.0%} | Reason: {c.confidence_reason}\n"
        f"Category: {c.category} | Urgency: {c.urgency} | Sentiment: {c.sentiment}\n"
        f"Reasoning: {c.reasoning}\n\n"
        f"Original report:\n{report.preprocessed.sanitized_text}"
    )
    await ctx.yield_output(output)


@executor(id="escalate_to_human")
async def escalate_to_human_executor(report: RoutedBugReport, ctx: WorkflowContext[None, str]) -> None:
    """Prints a human escalation summary for security/critical reports."""
    c = report.classification
    output = (
        "ESCALATED TO HUMAN\n"
        f"Category: {c.category} | Urgency: {c.urgency} | Sentiment: {c.sentiment}\n"
        f"Reasoning: {c.reasoning}\n"
        f"Decision: {report.decision.explanation}\n\n"
        f"Original report:\n{report.preprocessed.sanitized_text}"
    )
    await ctx.yield_output(output)


@executor(id="ask_for_missing_info")
async def ask_for_missing_info_executor(report: RoutedBugReport, ctx: WorkflowContext[None, str]) -> None:
    """Drafts a short customer reply asking for the missing fields."""
    c = report.classification
    missing_lines = "\n".join(f"- {field}" for field in c.missing_info)
    reply = (
        "Hi,\n\n"
        "Thanks for the report! To help us investigate, could you provide the "
        f"following details?\n{missing_lines}\n\n"
        "Thanks,\nSupport Team"
    )
    output = (
        "MORE INFO NEEDED - DRAFT CUSTOMER REPLY\n"
        f"Category: {c.category} | Urgency: {c.urgency}\n"
        f"Reasoning: {c.reasoning}\n\n"
        f"{reply}"
    )
    await ctx.yield_output(output)


@executor(id="create_developer_summary")
async def create_developer_summary_executor(report: RoutedBugReport, ctx: WorkflowContext[None, str]) -> None:
    """Produces a concise developer ticket summary."""
    c = report.classification
    p = report.preprocessed

    lines = [
        "DEVELOPER TICKET SUMMARY",
        f"Category: {c.category} | Urgency: {c.urgency} | Sentiment: {c.sentiment}",
    ]
    if p.extracted_version:
        lines.append(f"Version: {p.extracted_version}")
    if p.extracted_os:
        lines.append(f"OS: {p.extracted_os}")
    if p.has_stack_trace:
        lines.append("Stack trace included: yes")
    lines.append(f"Reasoning: {c.reasoning}")
    lines.append("")
    lines.append("Original report:")
    lines.append(p.sanitized_text)

    await ctx.yield_output("\n".join(lines))


class NeedsHumanApprovalExecutor(Executor):
    """Bonus: pauses for human approval before closing/rejecting a
    duplicate/spam/invalid report - the "risky action" gate.

    `propose` calls `ctx.request_info(...)`, which suspends the workflow and
    surfaces a `request_info` event in the stream. The CLI resumes the
    workflow with `workflow.run(stream=True, responses={request_id: bool})`,
    which dispatches to `on_approval` below.
    """

    def __init__(self) -> None:
        super().__init__(id="needs_human_approval_to_close")

    @handler
    async def propose(self, report: RoutedBugReport, ctx: WorkflowContext[ApprovalRequest]) -> None:
        c = report.classification
        summary = report.preprocessed.sanitized_text.strip().splitlines()[0]
        proposed_action = f"Close this report as {c.category}."

        await ctx.request_info(
            request_data=ApprovalRequest(
                summary=summary,
                category=c.category,
                proposed_action=proposed_action,
                reasoning=c.reasoning,
            ),
            response_type=bool,
        )

    @response_handler
    async def on_approval(
        self, original_request: ApprovalRequest, approved: bool, ctx: WorkflowContext[None, str]
    ) -> None:
        if approved:
            output = (
                "ACTION TAKEN: closed/rejected\n"
                f"Category: {original_request.category}\n"
                f"{original_request.proposed_action}\n"
                f"Reasoning: {original_request.reasoning}"
            )
        else:
            output = (
                "ACTION TAKEN: escalated_to_human_review\n"
                f"Category: {original_request.category}\n"
                f"A human reviewer rejected the proposed action "
                f"({original_request.proposed_action!r}); this report needs manual review."
            )
        await ctx.yield_output(output)
