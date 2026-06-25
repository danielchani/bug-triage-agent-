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

# Router threshold — keep in sync with router.py:LOW_CONFIDENCE_THRESHOLD
_LOW_CONFIDENCE_THRESHOLD = 0.60

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

- confidence: a float between 0.0 and 1.0 indicating how certain you are
  about this classification. Guidelines:
  - 0.85-1.0 (high): report is concrete, complete, and unambiguous.
  - 0.60-0.84 (medium): report is plausible but some details are unclear.
  - 0.0-0.59 (low): report is vague, contradictory, emotional, or could
    reasonably belong to multiple categories. Reports below 0.60 will be
    routed to human review rather than automated action.

- confidence_reason: a single sentence explaining why you assigned this
  confidence level (e.g. "All required fields are present and the failure
  mode is clear." or "Report is vague with no version, OS, or steps.").

- missing_info: a list of short strings naming details that would be needed
  to act on this report but are absent (e.g. "steps_to_reproduce", "version",
  "operating_system", "expected_vs_actual_behavior"). Use an empty list if the
  report is complete enough to act on, or if it isn't a real bug report at
  all (duplicate/spam/invalid).

- route: YOUR OWN BEST GUESS at one of "escalate_to_human",
  "ask_for_missing_info", "create_developer_summary",
  "needs_human_approval_to_close", "low_confidence_review". This is only a
  proposal - a separate deterministic router makes the final decision.

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

    # `BaseChatClient.as_agent(...)` is the current MAF way to get an Agent.
    # Both real and mock paths return the same BugClassification type.
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


# Confidence float values used by the mock classifier.
# Values above 0.60 (LOW_CONFIDENCE_THRESHOLD) proceed to normal routing;
# values below route to low_confidence_review.
_CONFIDENCE_STRONG_SIGNAL = 0.95  # keywords unambiguously match a category
_CONFIDENCE_COMPLETE = 0.90       # no missing fields
_CONFIDENCE_ONE_MISSING = 0.70    # one field absent (above threshold → ask for info)
_CONFIDENCE_TWO_MISSING = 0.65    # two fields absent (above threshold → ask for info)
_CONFIDENCE_VAGUE = 0.25          # three or more fields absent (below threshold → human review)


def _mock_confidence(missing_count: int, strong_signal: bool) -> float:
    if strong_signal:
        return _CONFIDENCE_STRONG_SIGNAL
    table = {0: _CONFIDENCE_COMPLETE, 1: _CONFIDENCE_ONE_MISSING, 2: _CONFIDENCE_TWO_MISSING}
    return table.get(missing_count, _CONFIDENCE_VAGUE)


def _mock_confidence_reason(missing_info: list[str], strong_signal: bool, category: str) -> str:
    if strong_signal:
        return f"Unambiguous keyword match for {category} category."
    n = len(missing_info)
    if n == 0:
        return "All required fields are present (version, OS, steps, expected/actual behaviour)."
    if n == 1:
        return f"One field is absent ({missing_info[0]}); report is mostly complete."
    if n == 2:
        return f"Two fields are absent ({', '.join(missing_info)}); report has most required context."
    return f"{n} key fields are absent ({', '.join(missing_info)}); report is too vague to classify with confidence."


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
        missing_info = _mock_missing_info(report, text)
        return BugClassification(
            category="security",
            urgency="critical",
            sentiment=_mock_sentiment(text),
            confidence=_mock_confidence(len(missing_info), strong_signal=True),
            confidence_reason="Unambiguous keyword match for security category.",
            missing_info=missing_info,
            route="escalate_to_human",
            reasoning="Mock classifier: text mentions security/bypass-related keywords; treated as critical.",
        )

    spam_keywords = ("% off", "discount", "promo code", "subscription", "limited time offer", "buy now")
    if any(kw in text for kw in spam_keywords):
        return BugClassification(
            category="spam",
            urgency="low",
            sentiment="calm",
            confidence=_CONFIDENCE_STRONG_SIGNAL,
            confidence_reason="Unambiguous keyword match for spam category.",
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
            confidence=_CONFIDENCE_STRONG_SIGNAL,
            confidence_reason="Unambiguous keyword match for duplicate category.",
            missing_info=[],
            route="needs_human_approval_to_close",
            reasoning="Mock classifier: report references an existing ticket/issue, likely a duplicate.",
        )

    missing_info = _mock_missing_info(report, text)
    urgency = "high" if any(kw in text for kw in ("crash", "asap", "urgent", "critical")) else "medium"
    route = "ask_for_missing_info" if missing_info else "create_developer_summary"
    conf = _mock_confidence(len(missing_info), strong_signal=False)
    conf_reason = _mock_confidence_reason(missing_info, strong_signal=False, category="bug")
    return BugClassification(
        category="bug",
        urgency=urgency,
        sentiment=_mock_sentiment(text),
        confidence=conf,
        confidence_reason=conf_reason,
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
