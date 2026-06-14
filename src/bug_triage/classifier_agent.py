"""Agent classifier node: produces a structured BugClassification for a
preprocessed bug report.

This is the only module in the project that talks to an LLM (per AGENTS.md).
It supports two modes, both with the same input/output types so the rest of
the workflow doesn't need to know which one is active:

- Real mode (default): builds an OpenAI-backed Agent via
  `OpenAIChatClient(...).as_agent(...)` with `response_format=BugClassification`
  and calls it directly with `agent.run(...)`.
- Mock mode (BUG_TRIAGE_MOCK_LLM=true): returns a deterministic, keyword-based
  BugClassification with no network access. Intended for offline development
  and tests; real agent mode is the intended homework run.

The classifier proposes its own best-guess `route`, but never performs
routing itself - router.py's `decide_route` is the final authority.
"""

import os

from agent_framework import WorkflowContext, executor
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

from bug_triage.models import BugClassification, ClassifiedBugReport, PreprocessedBugReport, SentimentLevel

load_dotenv()

DEFAULT_MODEL_ID = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are a bug triage assistant for a software team.

You will be given a preprocessed bug report: its sanitized text, plus a few
signals already extracted from it (whether an email/issue reference/version/
OS was detected, and whether a stack trace is present).

Classify the report using these fields:

- category: one of "bug", "security", "performance", "feature_request",
  "duplicate", "spam", "invalid", "other".
    - "security": a vulnerability, exploit, or unauthorized-access issue.
    - "duplicate": the reporter references an existing/known issue.
    - "spam": promotional or unrelated content submitted through the bug form.
    - "invalid": not a real, actionable bug report (e.g. unintelligible, or
      "working as intended").
    - "bug": a genuine functional defect (the common case).

- urgency: one of "low", "medium", "high", "critical".
  Use "critical" for security issues, outages, or data loss.

- sentiment: one of "calm", "frustrated", "angry" - the reporter's tone.

- missing_info: a list of short strings naming details that would be needed
  to act on this report but are absent (e.g. "steps_to_reproduce", "version",
  "operating_system", "expected_vs_actual_behavior"). Use an empty list if the
  report is complete enough to act on, or if it isn't a real bug report at
  all (duplicate/spam/invalid).

- route: YOUR OWN BEST GUESS at one of "escalate_to_human",
  "ask_for_missing_info", "create_developer_summary",
  "needs_human_approval_to_close". This is only a proposal - a separate
  deterministic router makes the final decision, so do your best but don't
  worry about perfectly matching the rules above.

- reasoning: a short (1-2 sentence) explanation of your classification.

Respond only with the structured BugClassification fields.
"""


def _is_mock_mode() -> bool:
    return os.environ.get("BUG_TRIAGE_MOCK_LLM", "").strip().lower() in {"1", "true", "yes"}


def _build_prompt(report: PreprocessedBugReport) -> str:
    return "\n".join(
        [
            "Bug report text:",
            report.sanitized_text,
            "",
            f"Detected email present: {report.extracted_email is not None}",
            f"Detected issue/ticket reference: {report.extracted_issue_id or 'none'}",
            f"Detected version: {report.extracted_version or 'none'}",
            f"Detected OS: {report.extracted_os or 'none'}",
            f"Stack trace present: {report.has_stack_trace}",
        ]
    )


async def _real_classify(report: PreprocessedBugReport, model_id: str | None) -> BugClassification:
    resolved_model_id = model_id or os.environ.get("OPENAI_CHAT_MODEL_ID", DEFAULT_MODEL_ID)
    client = OpenAIChatClient(model=resolved_model_id)

    # API note: `BaseChatClient.as_agent(...)` is the current MAF way to get an
    # Agent (older examples referencing `ChatAgent` no longer apply). We call the
    # Agent directly with `agent.run(...)` rather than wrapping it in an
    # AgentExecutor, so this function and `_mock_classify` below return the exact
    # same `BugClassification` type regardless of mode - the rest of the
    # workflow graph is identical either way.
    agent = client.as_agent(
        name="bug-triage-classifier",
        instructions=SYSTEM_PROMPT,
        default_options={"response_format": BugClassification},
    )
    response = await agent.run(_build_prompt(report))
    if response.value is not None:
        return response.value
    return BugClassification.model_validate_json(response.text)


def _mock_missing_info(report: PreprocessedBugReport, text: str) -> list[str]:
    missing: list[str] = []
    if report.extracted_version is None:
        missing.append("version")
    if report.extracted_os is None:
        missing.append("operating_system")
    if "steps to reproduce" not in text and "steps:" not in text:
        missing.append("steps_to_reproduce")
    if "expected" not in text or "actual" not in text:
        missing.append("expected_vs_actual_behavior")
    return missing


def _mock_sentiment(text: str) -> SentimentLevel:
    if any(kw in text for kw in ("unacceptable", "furious", "outrageous", "terrible")):
        return "angry"
    if any(kw in text for kw in ("annoying", "frustrat", "please fix", "asap", "again", "still happening")):
        return "frustrated"
    return "calm"


def _mock_classify(report: PreprocessedBugReport) -> BugClassification:
    """Deterministic, keyword-based stand-in for the real LLM classifier."""
    text = report.sanitized_text.lower()

    security_keywords = ("security", "vulnerability", "exploit", "bypass", "unauthorized", "csrf", "xss", "injection")
    if any(kw in text for kw in security_keywords):
        return BugClassification(
            category="security",
            urgency="critical",
            sentiment=_mock_sentiment(text),
            missing_info=_mock_missing_info(report, text),
            route="escalate_to_human",
            reasoning="Mock classifier: text mentions security/bypass-related keywords; treated as critical.",
        )

    spam_keywords = ("% off", "discount", "promo code", "subscription", "limited time offer", "buy now")
    if any(kw in text for kw in spam_keywords):
        return BugClassification(
            category="spam",
            urgency="low",
            sentiment="calm",
            missing_info=[],
            route="needs_human_approval_to_close",
            reasoning="Mock classifier: text looks like promotional/spam content, not a bug report.",
        )

    duplicate_keywords = ("duplicate", "already reported", "reported this", "same issue", "known issue")
    if report.extracted_issue_id or any(kw in text for kw in duplicate_keywords):
        return BugClassification(
            category="duplicate",
            urgency="low",
            sentiment=_mock_sentiment(text),
            missing_info=[],
            route="needs_human_approval_to_close",
            reasoning="Mock classifier: report references an existing ticket/issue, likely a duplicate.",
        )

    missing_info = _mock_missing_info(report, text)
    urgency = "high" if any(kw in text for kw in ("crash", "asap", "urgent", "critical")) else "medium"
    route = "ask_for_missing_info" if missing_info else "create_developer_summary"
    return BugClassification(
        category="bug",
        urgency=urgency,
        sentiment=_mock_sentiment(text),
        missing_info=missing_info,
        route=route,
        reasoning="Mock classifier: generic bug report; route guess based on whether key details are present.",
    )


@executor(id="classifier")
async def classifier_executor(report: PreprocessedBugReport, ctx: WorkflowContext[ClassifiedBugReport]) -> None:
    if _is_mock_mode():
        classification = _mock_classify(report)
    else:
        classification = await _real_classify(report, model_id=None)

    await ctx.send_message(ClassifiedBugReport(preprocessed=report, classification=classification))
