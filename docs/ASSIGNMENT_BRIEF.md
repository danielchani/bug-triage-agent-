# Assignment Brief

## Original task

Build a **Bug Report Triage Workflow Agent** using the Microsoft Agent Framework (MAF). The agent should accept a raw bug report and automatically classify, route, and act on it — demonstrating agentic workflow composition, structured LLM output, and human-in-the-loop design.

### Core requirements

- Deterministic preprocessing step (email masking, signal extraction)
- LLM-based classification with a **typed, structured schema** (`response_format` / Pydantic model)
- **Enum/Literal taxonomy** for `category`, `urgency`, `sentiment` — no free-form strings
- **Separation of concerns**: classifier proposes a route; a separate deterministic function makes the final decision
- At least four distinct routes with appropriate actions
- **Human-in-the-loop gate** for risky actions (closing/rejecting a report)
- **Clean failure paths** for missing or invalid API keys
- Offline mock mode for development and testing without API calls

---

## Reviewer feedback (Alexey)

> Add an explicit confidence signal to `BugClassification` so ambiguous reports are caught directly, rather than only inferred from `missing_info` plus the approval gate.

---

## What was implemented (and how feedback was addressed)

| Requirement | Status | Notes |
|---|---|---|
| Structured LLM output with `response_format` | ✅ | `BugClassification` Pydantic model; `confidence` field added per feedback |
| Enum/Literal taxonomy | ✅ | `BugCategory`, `UrgencyLevel`, `SentimentLevel`, `ConfidenceLevel`, `RouteName` |
| Classifier proposes, router decides | ✅ | `router.py:decide_route()` is the sole routing authority |
| **Explicit confidence signal** (Alexey's feedback) | ✅ | `BugClassification.confidence: Literal["low","medium","high"]`; `"low"` routes directly to human review — no inference needed |
| Clean failure paths | ✅ | Missing `OPENAI_API_KEY` raises `openai.AuthenticationError` at classifier time; set `BUG_TRIAGE_MOCK_LLM=true` to bypass |
| Human-in-the-loop for risky close/reject | ✅ | MAF `request_info` / `response_handler` pattern in `actions.py` |
| Deterministic red-flag rules | ✅ | `red_flags.py` — RF001–RF004 regex rules run at preprocess time and override the LLM unconditionally |
| Low-confidence escalation | ✅ | Router rule #2: `confidence == "low"` → `escalate_to_human` |
| Real input surface (file, stdin, batch, CSV) | ✅ | `main.py` supports single file, `-` for stdin, `--batch <folder>`, `--csv <file>` |
| Decision audit log | ✅ | `audit_log.py` — JSONL, one entry per run, includes `human_decision` for approval flows |
| Docker / one-command run | ✅ | `Dockerfile` + `docker-compose.yml`; `docker compose run bug-triage samples/foo.txt` |
| Improved README | ✅ | Tech stack, architecture diagram with confidence/red-flag nodes, quick start, env vars, sample I/O, test instructions, quality gates, known limitations, future improvements |
| No secrets committed | ✅ | `.env`, `triage_audit.jsonl`, `dist/`, `*.egg-info` all gitignored |

### Routing priority (final)

```
0. red_flags_triggered non-empty   → escalate_to_human  (hard override)
1. security or critical urgency    → escalate_to_human
2. confidence == "low"             → escalate_to_human  (Alexey's feedback)
3. missing_info non-empty          → ask_for_missing_info
4. duplicate / spam / invalid      → needs_human_approval_to_close
5. otherwise                       → create_developer_summary
```
