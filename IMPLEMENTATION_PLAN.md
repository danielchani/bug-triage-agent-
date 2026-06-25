# Implementation Plan — Bug Triage Agent Portfolio Upgrade

Upgrading `danielchani/bug-triage-maf-workflow` → `danielchani/bug-triage-agent`.

## Phase 1 — Models: Add `confidence` to `BugClassification` ✅

- [x] Add `ConfidenceLevel = Literal["low", "medium", "high"]` to `models.py`
- [x] Add `confidence: ConfidenceLevel` field to `BugClassification`
- [x] Add `red_flags_triggered: list[str]` field to `PreprocessedBugReport`
- [x] Update `SYSTEM_PROMPT` in `classifier_agent.py` to request `confidence`
- [x] Update `_mock_classify` to compute confidence (high/medium/low by missing-field count)
- [x] Add low-confidence routing rule to `router.py` (priority #2, after security check)
- [x] Update all test fixtures and add new test cases

**Commit:** `feat(models): add confidence field and red_flags_triggered to models`

## Phase 2 — Deterministic Red-Flag Rules ✅

- [x] Create `src/bug_triage/red_flags.py` with `RedFlagRule` dataclass and `check_red_flags()`
- [x] RF001: SQL injection / XSS / RCE / CSRF
- [x] RF002: Data breach / GDPR / PII exposure
- [x] RF003: Service outage / production down / all users affected
- [x] RF004: Authentication bypass / privilege escalation / zero-day / account takeover
- [x] Call `check_red_flags()` in `preprocess.py`; store rule IDs in `red_flags_triggered`
- [x] Update `decide_route()` in `router.py` to accept optional `preprocessed` and check red flags first (priority #0)
- [x] Create `tests/test_red_flags.py` with parametrized hit/miss tests and router integration tests

**Commit:** `feat(red-flags): add deterministic red-flag pattern rules`

## Phase 3 — Decision Audit Log ✅

- [x] Create `src/bug_triage/audit_log.py` with `AuditEntry` model and `append_audit_entry()`
- [x] Wire audit log into `main.py` (write entry after each run, including `human_decision`)
- [x] Add `--no-audit` flag to suppress logging
- [x] Support `TRIAGE_AUDIT_LOG` env var for custom log path
- [x] Add `triage_audit.jsonl` to `.gitignore`
- [x] Create `tests/test_audit_log.py`

**Commit:** `feat(audit): add JSONL decision audit log`

## Phase 4 — Expanded Input Surface ✅

- [x] Add stdin support (`-`) to `main.py`
- [x] Add `--batch <folder>` mode (processes all `.txt` files)
- [x] Add `--csv <file>` mode (column aliases: text, body, description, report)
- [x] Create `samples/batch_sample.csv` with 3-row demo
- [x] Create `tests/test_batch.py`

**Commit:** `feat(input): add stdin, batch folder, and CSV input modes`

## Phase 5 — Docker ✅

- [x] Create `Dockerfile` (Python 3.12-slim, `pip install -e .`)
- [x] Create `docker-compose.yml` (mounts `samples/` readonly, `stdin_open: true`)
- [x] Create `.dockerignore`

**Commit:** `feat(docker): add Dockerfile and docker-compose for one-command run`

## Phase 6 — Documentation ✅

- [x] Overhaul `README.md`: tech stack, architecture diagram, quick start (Docker + local), env vars table, all input modes, sample I/O, test instructions, routing table, audit log format, project structure, quality gates, known limitations, future improvements, security notes
- [x] Fill in `docs/ASSIGNMENT_BRIEF.md`: original requirements, Alexey's feedback, implementation status checklist
- [x] Create `IMPLEMENTATION_PLAN.md` (this file)

**Commit:** `docs: overhaul README, fill assignment brief, add implementation plan`

## Phase 7 — New repo push (manual)

```bash
gh repo create danielchani/bug-triage-agent --public \
  --description "Bug report triage workflow agent — MAF + OpenAI + Pydantic"
git remote set-url origin https://github.com/danielchani/bug-triage-agent.git
git push -u origin main
```

---

## Verification commands

```bash
# All tests (offline, no API key needed)
pytest

# Single file
python -m bug_triage.main samples/complete_bug.txt --no-audit

# Batch
python -m bug_triage.main --batch samples/ --no-audit

# CSV
python -m bug_triage.main --csv samples/batch_sample.csv --no-audit

# Stdin
echo "JWT bypass found in /api/auth" | python -m bug_triage.main - --no-audit

# Docker
docker compose build
docker compose run -e BUG_TRIAGE_MOCK_LLM=true bug-triage samples/complete_bug.txt
```

## Test count

| Phase | Tests |
|---|---|
| Baseline | 52 |
| After Phase 1 (confidence) | 59 |
| After Phase 2 (red flags) | 81 |
| After Phases 3–4 (audit + batch) | 96 |
