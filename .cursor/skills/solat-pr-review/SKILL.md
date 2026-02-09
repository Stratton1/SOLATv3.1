---
name: solat-pr-review
description: Runs pre-PR checklist: conventions on changed files, secrets check, tests for engine/api, docs for behaviour changes, ROADMAP tick if phase deliverable. Use when reviewing PR or checking changes before push.
---

# SOLAT PR / Change Review Agent (11.1)

When the user says **"Review this PR"**, **"Check my changes"**, or before pushing, run this **checklist** and return **results and concrete suggestions**. Optionally read diff or list of files and suggest fixes.

## Checklist

### Conventions

- [ ] **Python (engine):** Changed engine/**/*.py follows [docs/CONVENTIONS.md](docs/CONVENTIONS.md): ruff, mypy, naming (snake_case/PascalCase), Decimal for money, structured logging, no secrets in logs.
- [ ] **TypeScript/React (desktop):** Changed apps/desktop/src/** follows CONVENTIONS: PascalCase components, use* hooks, named exports, props interface, no any.

### Security

- [ ] **Secrets:** No hardcoded API keys, passwords, or tokens; no logging of request/response with auth; no credentials in error messages. Use env/SecretStr and redact_sensitive().

### Tests

- [ ] **Engine/api changes:** If engine or api code changed, were tests added or updated? (engine/tests/test_*.py). Suggest adding test for new route or module if missing.
- [ ] **Existing tests:** Do existing tests still pass? (pnpm test:engine, pnpm typecheck.)

### Documentation

- [ ] **Behaviour change:** If behaviour or API contract changed, were docs updated? (ARCHITECTURE, ROADMAP, CONVENTIONS, SECURITY, README.) Suggest doc edits if applicable.
- [ ] **ROADMAP:** If a phase deliverable was completed, suggest ticking the box in [docs/ROADMAP.md](docs/ROADMAP.md) and optionally adding a [BUILD_LOG.md](BUILD_LOG.md) entry.

## Output

1. **Per item:** Pass / Fail / N/A (with one-line reason).
2. **Suggestions:** Concrete fix (e.g. "Add test_my_module.py for engine/solat_engine/my_module.py", "Remove logger.info(request) and use redact_sensitive()").
3. **Optional:** If user provides diff or file list, reference specific files in suggestions.

Do not block or enforce; output checklist and suggestions only.
