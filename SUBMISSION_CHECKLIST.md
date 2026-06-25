# Submission Checklist

Complete this before submitting the GitHub repo URL.

---

## Quality gate results

### Tests
```
py -m pytest
```
**Result:** 134 passed, 0 failed, 2 warnings (ExperimentalWarning from MAF internals — not our code)

### Lint
```
ruff check src/ tests/
```
**Result:** All checks passed

### Docker build
```
docker build -t bug-triage-agent .
```
**Result:** _(run this locally — no Docker available in this environment)_

### Docker smoke run (mock mode)
```
docker run --rm -e BUG_TRIAGE_MOCK_LLM=true bug-triage-agent samples/complete_bug.txt
```
**Expected output:** `[output] create_developer_summary: DEVELOPER TICKET SUMMARY ...`

---

## Secrets check

### .env not tracked
```
git status
```
**Result:** `.env` does not appear in tracked files ✅

### .env.example is tracked
```
git ls-files .env.example
```
**Result:** `.env.example` is tracked ✅

### No secrets in code
```
git grep -n "sk-"
git grep -n "OPENAI_API_KEY="
git grep -n "api_key\s*="
git grep -n "password\s*="
```
**Result:** No matches ✅

---

## Generated junk check

```
git status --ignored
```

Verify none of the following are tracked:
- [ ] `.venv/`
- [ ] `__pycache__/`
- [ ] `*.pyc`
- [ ] `*.egg-info/`
- [ ] `.pytest_cache/`
- [ ] `dist/`
- [ ] `triage_audit.jsonl`

---

## README claims vs code

| Claim | Verified |
|---|---|
| Docker one-command run | ✅ Dockerfile + docker-compose.yml present |
| 134 tests, all offline | ✅ `pytest` confirms |
| Confidence field (float 0–1) | ✅ `BugClassification.confidence: float = Field(ge=0.0, le=1.0)` |
| `low_confidence_review` route | ✅ in `RouteName`, executor, workflow |
| Red-flag rules RF001–RF005 | ✅ `src/bug_triage/red_flags.py` |
| JSONL audit log | ✅ `src/bug_triage/audit_log.py`, `--audit-log` flag |
| Stdin + batch + CSV input | ✅ `--stdin`, `--batch`, `--csv` flags |
| GitHub Actions CI | ✅ `.github/workflows/ci.yml` |
| No secrets committed | ✅ `.gitignore` covers `.env`, `triage_audit.jsonl`, artifacts |

---

## Repo URL to submit

```
https://github.com/danielchani/bug-triage-agent-
```

---

## Final pre-submission git state

```
git log --oneline
git status
```

Expected: clean working tree, all changes committed, `main` branch up to date with origin.
