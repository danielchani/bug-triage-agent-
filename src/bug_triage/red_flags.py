"""Deterministic red-flag rules that run on the sanitized text before LLM routing.

Each rule is a compiled regex with a stable ID. Triggered rules are stored on
PreprocessedBugReport.red_flags_triggered and checked by the router *before*
any LLM-based routing, giving them hard override authority.

Rule catalogue:
  RF001 — Security attack vectors: SQL injection, XSS, RCE, CSRF, API key/token leak
  RF002 — Data risk: data breach, PII/GDPR, wrong user data, data loss
  RF003 — Production impact: service outage, production down, all users affected, cannot login
  RF004 — Auth risk: authentication bypass, privilege escalation, zero-day, account takeover
  RF005 — Payment risk: double charge, unauthorized charge, billing error
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RedFlagRule:
    rule_id: str
    description: str
    pattern: re.Pattern[str]


@dataclass
class RedFlagResult:
    """Aggregated result of evaluating all red-flag rules against a text."""

    flags: list[str] = field(default_factory=list)
    forced_route: str | None = None
    reason: str | None = None


_RULES: list[RedFlagRule] = [
    RedFlagRule(
        rule_id="RF001",
        description="Security attack vector: SQL injection / XSS / RCE / CSRF / token/key leak",
        pattern=re.compile(
            r"\b(sql\s*injection|cross[- ]site\s+script|xss|remote\s+code\s+exec(?:ution)?|rce|csrf"
            r"|api\s+key\s+(?:\w+\s+){0,2}(?:exposed?|leaked?)|token\s+(?:\w+\s+){0,2}(?:exposed?|leaked?))\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF002",
        description="Data risk: data breach / PII / GDPR / wrong user data / data loss",
        pattern=re.compile(
            r"\b(data\s+breach|personal\s+data|pii|gdpr|user\s+data\s+leak(?:ed)?"
            r"|exposed?\s+credentials?|wrong\s+user(?:'s)?\s+data|users?\s+(?:can\s+)?see\s+other\s+users?"
            r"|data\s+loss)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF003",
        description="Production impact: service outage / production down / all users affected / cannot login",
        pattern=re.compile(
            r"\b(service\s+outage|production\s+(?:is\s+)?down|all\s+users?\s+(?:are\s+)?affected"
            r"|site[- ]wide\s+outage|cannot\s+log\s*in|no\s+one\s+can\s+log\s*in)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF004",
        description="Auth risk: authentication bypass / privilege escalation / zero-day / account takeover",
        pattern=re.compile(
            r"\b(auth(?:entication)?\s+bypass|privilege\s+escalation|zero[- ]day|0[- ]day|account\s+takeover)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF005",
        description="Payment risk: double charge / unauthorized charge / billing error",
        pattern=re.compile(
            r"\b(double\s+charge[d]?|charged\s+(?:\w+\s+){0,2}twice|unauthorized\s+charge[d]?"
            r"|billed?\s+twice|duplicate\s+(?:charge|payment)|payment\s+taken\s+twice)\b",
            re.IGNORECASE,
        ),
    ),
]


def check_red_flags(text: str) -> list[RedFlagRule]:
    """Return all rules triggered by `text`. Empty list = no red flags.

    Use this for unit testing individual rules. For routing, use evaluate_red_flags.
    """
    return [rule for rule in _RULES if rule.pattern.search(text)]


def evaluate_red_flags(text: str) -> RedFlagResult:
    """Evaluate all rules and return an aggregated RedFlagResult.

    If any rule fires, forced_route is set to "escalate_to_human".
    """
    triggered = check_red_flags(text)
    if not triggered:
        return RedFlagResult()

    flags = [r.rule_id for r in triggered]
    descriptions = "; ".join(r.description for r in triggered)
    return RedFlagResult(
        flags=flags,
        forced_route="escalate_to_human",
        reason=f"Deterministic red-flag rules triggered ({', '.join(flags)}): {descriptions}.",
    )
