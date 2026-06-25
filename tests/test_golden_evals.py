"""Golden eval tests — labeled hard cases run against the mock classifier.

Each case in evals/golden_cases.jsonl is loaded and asserted against
expected category, route, confidence bounds, and red flags.

All tests are offline (BUG_TRIAGE_MOCK_LLM=true implied by mock classifier).
"""

import json
from pathlib import Path

import pytest

from bug_triage.classifier_agent import _mock_classify
from bug_triage.models import BugReportInput
from bug_triage.preprocess import preprocess
from bug_triage.router import decide_route

_EVALS_PATH = Path(__file__).parent.parent / "evals" / "golden_cases.jsonl"


def _load_cases():
    with _EVALS_PATH.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _triage(raw_text: str):
    preprocessed = preprocess(BugReportInput(raw_text=raw_text))
    classification = _mock_classify(preprocessed)
    decision = decide_route(classification, preprocessed)
    return preprocessed, classification, decision


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_golden_case(case):
    """Assert that each labeled golden case produces the expected routing outcome."""
    preprocessed, classification, decision = _triage(case["raw_text"])

    assert classification.category == case["expected_category"], (
        f"[{case['id']}] category: got {classification.category!r}, expected {case['expected_category']!r}\n"
        f"  reasoning: {classification.reasoning}"
    )

    assert decision.route == case["expected_route"], (
        f"[{case['id']}] route: got {decision.route!r}, expected {case['expected_route']!r}\n"
        f"  confidence={classification.confidence:.2f}, explanation={decision.explanation}"
    )

    assert case["expected_min_confidence"] <= classification.confidence <= case["expected_max_confidence"], (
        f"[{case['id']}] confidence {classification.confidence:.2f} not in "
        f"[{case['expected_min_confidence']}, {case['expected_max_confidence']}]"
    )

    for expected_flag in case["expected_red_flags"]:
        assert expected_flag in preprocessed.red_flags_triggered, (
            f"[{case['id']}] expected red flag {expected_flag!r} but got {preprocessed.red_flags_triggered}"
        )
