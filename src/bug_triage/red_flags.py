"""Deterministic red-flag rules that run on the sanitized text before (or after)
LLM classification.

Each rule is a compiled regex with a stable ID. Triggered rules are stored on
PreprocessedBugReport.red_flags_triggered and checked by the router *before*
any LLM-based routing, giving them hard override authority.

Rule catalogue:
  RF001 — SQL injection / XSS / RCE / CSRF keywords
  RF002 — Data breach / GDPR / PII exposure
  RF003 — Service outage / production down / all users affected
  RF004 — Authentication bypass / privilege escalation / zero-day
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedFlagRule:
    rule_id: str
    description: str
    pattern: re.Pattern[str]


_RULES: list[RedFlagRule] = [
    RedFlagRule(
        rule_id="RF001",
        description="Web attack vector: SQL injection / XSS / RCE / CSRF",
        pattern=re.compile(
            r"\b(sql\s*injection|cross[- ]site\s+script|xss|remote\s+code\s+exec(?:ution)?|rce|csrf)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF002",
        description="Data breach / GDPR / PII exposure",
        pattern=re.compile(
            r"\b(data\s+breach|personal\s+data|pii|gdpr|user\s+data\s+leak(?:ed)?|exposed?\s+credentials?)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF003",
        description="Service outage / production down / all users affected",
        pattern=re.compile(
            r"\b(service\s+outage|production\s+(?:is\s+)?down|all\s+users?\s+(?:are\s+)?affected|site[- ]wide\s+outage)\b",
            re.IGNORECASE,
        ),
    ),
    RedFlagRule(
        rule_id="RF004",
        description="Authentication bypass / privilege escalation / zero-day",
        pattern=re.compile(
            r"\b(auth(?:entication)?\s+bypass|privilege\s+escalation|zero[- ]day|0[- ]day|account\s+takeover)\b",
            re.IGNORECASE,
        ),
    ),
]


def check_red_flags(text: str) -> list[RedFlagRule]:
    """Return all rules triggered by `text` (case-insensitive). Empty list = no red flags."""
    return [rule for rule in _RULES if rule.pattern.search(text)]
