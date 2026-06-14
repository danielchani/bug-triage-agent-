"""Assembles the bug-triage workflow graph.

    preprocess -> classifier -> router -> (switch-case on RouteDecision.route)
                                              |-- escalate_to_human
                                              |-- ask_for_missing_info
                                              |-- needs_human_approval_to_close
                                              `-- create_developer_summary (default)
"""

from agent_framework import Case, Default, Workflow, WorkflowBuilder

from bug_triage.actions import (
    NeedsHumanApprovalExecutor,
    ask_for_missing_info_executor,
    create_developer_summary_executor,
    escalate_to_human_executor,
)
from bug_triage.classifier_agent import classifier_executor
from bug_triage.preprocess import preprocess_executor
from bug_triage.router import router_executor


def build_workflow() -> Workflow:
    needs_approval_executor = NeedsHumanApprovalExecutor()

    return (
        WorkflowBuilder(start_executor=preprocess_executor, output_from="all")
        .add_edge(preprocess_executor, classifier_executor)
        .add_edge(classifier_executor, router_executor)
        .add_switch_case_edge_group(
            router_executor,
            [
                Case(
                    condition=lambda r: r.decision.route == "escalate_to_human",
                    target=escalate_to_human_executor,
                ),
                Case(
                    condition=lambda r: r.decision.route == "ask_for_missing_info",
                    target=ask_for_missing_info_executor,
                ),
                Case(
                    condition=lambda r: r.decision.route == "needs_human_approval_to_close",
                    target=needs_approval_executor,
                ),
                Default(target=create_developer_summary_executor),
            ],
        )
        .build()
    )
