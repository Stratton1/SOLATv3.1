# SOLAT v3.1 — Cursor Agents Inventory

A comprehensive list of agents (rules, skills, or agent configurations) for SOLAT development. For each agent: **why we need it**, **what it does**, **how it operates**, **when it triggers**, and **inputs/outputs** where relevant.

## Implementation status

All agents below are **implemented** as Cursor rules (`.cursor/rules/*.mdc`) or skills (`.cursor/skills/<name>/SKILL.md`). The **File** column in the [Summary Table](#12-summary-table) lists the path for each.

- **Rules:** 21 files in `.cursor/rules/` (always-on or file-scoped via globs).
- **Skills:** 21 skills in `.cursor/skills/<name>/SKILL.md` (on-demand; some agents are rule-only or skill-only).
- **Companion:** `solat-context` (Session Primer) is an optional skill; `solat-project-context` is the always-on rule.

---

## 1. **Project** & Context Agents

### 1.1 SOLAT Project Context Agent
- **Implemented:** `.cursor/rules/solat-project-context.mdc` (always-on).
- **Why:** Ensures every session has consistent understanding of what SOLAT is, its architecture, and current phase so suggestions stay aligned.
- **What:** Injects project identity (trading terminal, Tauri + React + Python FastAPI sidecar, IG broker, Elite 8, backtest-first), repo layout (`apps/desktop`, `engine/solat_engine`), and pointer to ROADMAP/ARCHITECTURE.
- **How:** Always-apply rule or short skill; no tool use. Pure context.
- **When:** Every conversation in this workspace.
- **Input:** None (context only). **Output:** N/A (agent behaviour is constrained by the context).

### 1.2 ROADMAP & Phase Agent
- **Implemented:** `.cursor/skills/solat-roadmap-phase/SKILL.md`.
- **Why:** Stops work that belongs in a later phase; suggests the right next steps from ROADMAP; keeps ROADMAP and code reality in sync; maintains an auditable build log.
- **What:** Knows phases 001–009 (Foundations) through 080+ (Live); knows which phases are done in code vs doc; can suggest “update ROADMAP” or “next: Terminal UI charting”; warns if adding live-only features before hardening. **Also updates `BUILD_LOG.md` (repo root)** when phase deliverables are completed, ROADMAP is edited, or “what’s next” is answered—so there is a dated record of what was built and when. Entries are reverse chronological (newest first).
- **How:** Rule or skill with ROADMAP summary + “current implementation state” (from last audit). When suggesting or applying ROADMAP/phase changes: (1) tick deliverables that exist in code; (2) insert a dated entry at the top of `BUILD_LOG.md` (repo root), reverse chronological (e.g. date, phase or task, what changed—ROADMAP tick, new deliverable, or “next steps” decision). Optional: when user says “log this” or “update build log”, write only the build_log entry.
- **When:** When user asks “what’s next”, “should I build X”, or when editing `docs/ROADMAP.md`. Build_log is updated whenever the agent proposes or applies ROADMAP/phase-related changes.
- **Input:** Optional: file path or “what phase is X in”. **Output:** Phase status, next suggested tasks, ROADMAP edit suggestions, and (when applicable) a new build_log entry or the updated `BUILD_LOG.md` (root) snippet.

### 1.3 Architecture Navigator Agent
- **Implemented:** `.cursor/skills/solat-architecture-navigator/SKILL.md`.
- **Why:** New contributors (or AI) need to know where to put code and how components connect without reading every file.
- **What:** Maps capability → location: e.g. “IG auth” → `engine/solat_engine/broker/ig/client.py`, “backtest API” → `api/backtest_routes.py`, “domain order” → `domain/order.py`. Knows data flow (ARCHITECTURE.md) and “engine talks to IG, UI talks only to engine”.
- **How:** Skill with small capability→path table + pointer to ARCHITECTURE.md. No codegen; navigation only.
- **When:** “Where does X live?”, “Where should I add Y?”, “How does market data get to the strategy?”
- **Input:** Concept or feature name. **Output:** File/dir paths and one-line role.

---

## 2. Convention & Style Agents

### 2.1 Python (Engine) Conventions Agent
- **Implemented:** `.cursor/rules/solat-python-conventions.mdc`.
- **Why:** CONVENTIONS.md and .cursorrules define engine style; an agent enforces it so PRs don’t drift (ruff, mypy, naming, Decimal, logging, exceptions).
- **What:** Enforces: ruff format/check, mypy strict; `snake_case` modules/functions, `PascalCase` classes, `SCREAMING_SNAKE_CASE` constants; Pydantic for domain; `Decimal` for price/qty; no float for money; structured logging; no secrets in logs; specific exceptions; pytest layout.
- **How:** File-specific rule for `engine/**/*.py` (and optionally `engine/tests/**/*.py`). When generating or editing Python in engine, apply these rules.
- **When:** Any edit or generation under `engine/`.
- **Input:** Code or diff. **Output:** Same code adjusted to conventions or list of violations.

### 2.2 TypeScript / React (Desktop) Conventions Agent
- **Implemented:** `.cursor/rules/solat-ts-react-conventions.mdc`.
- **Why:** UI has its own style: PascalCase components, `use*` hooks, named exports, props interfaces, no prop drilling beyond 2 levels.
- **What:** Enforces: Prettier/ESLint; PascalCase for components/files, camelCase for utils; hooks `use*`; types/interfaces PascalCase; props interface above component; named exports; hooks for state.
- **How:** File-specific rule for `apps/desktop/src/**/*.{ts,tsx}`.
- **When:** Any edit or generation under `apps/desktop/src/`.
- **Input:** Code or diff. **Output:** Conventions-compliant code or violations.

### 2.3 Naming & File Layout Agent
- **Implemented:** `.cursor/rules/solat-naming-layout.mdc` (always-on).
- **Why:** .cursorrules and CONVENTIONS specify kebab-case dirs, PascalCase components, camelCase vars; consistent layout speeds navigation.
- **What:** Validates/suggests: directories `kebab-case`; React components `PascalCase.tsx`; hooks `useCamelCase`; engine modules `snake_case.py`; no `any`; env vars `UPPER_SNAKE_CASE`. Knows SOLAT layout (e.g. `engine/solat_engine/<domain>/`, `apps/desktop/src/components/`).
- **How:** Rule (always or when creating/moving files). Can run on file paths and symbol names.
- **When:** Creating files, renaming, or when user asks “what should I name X?”
- **Input:** Path or symbol name. **Output:** Suggested name or list of renames.

### 2.4 Git & Commit Agent
- **Implemented:** `.cursor/skills/solat-git-commit/SKILL.md`.
- **Why:** Conventional commits and branch strategy (main, develop, feature/*, fix/*) keep history scannable and CI/tooling happy.
- **What:** Suggests commit message from diff: `feat(scope): description`, `fix(scope):`, `docs:`, `test(scope):`; scope = engine | ui | desktop | docs | ci; present tense, imperative. Optionally reminds about branch naming.
- **How:** Skill: “Given this diff/summary, output a commit message.” Optional rule when committing.
- **When:** User says “commit message”, “suggest commit”, or runs a commit workflow.
- **Input:** Diff or short summary. **Output:** One or more conventional commit lines.

---

## 3. Domain & Trading Agents

### 3.1 Domain Model Agent (Engine)
- **Implemented:** `.cursor/rules/solat-domain-model.mdc`.
- **Why:** Bar, Instrument, Signal, Order, Fill, Position must stay consistent: Decimal, Pydantic, frozen where possible, UUID vs str IDs. Prevents accidental float or mutable bugs.
- **What:** When touching `engine/solat_engine/domain/` or any code that creates/uses these types: enforce Pydantic BaseModel, Decimal for price/quantity/amount, frozen where appropriate, UUID internal IDs and str broker IDs; no new domain types without explicit need.
- **How:** Rule for `engine/solat_engine/domain/**` and optionally for files that import from `solat_engine.domain`.
- **When:** Editing domain models or code that constructs Bar, Order, Fill, Position, Signal, Instrument.
- **Input:** Snippet or file. **Output:** Corrected types and field types.

### 3.2 Backtest Integrity Agent
- **Implemented:** `.cursor/skills/solat-backtest-integrity/SKILL.md`.
- **Why:** Backtests must be deterministic and free of lookahead; otherwise results are invalid.
- **What:** Checks: no future data in strategy/simulator; bar iteration is time-ordered and single-pass; no “peeking” at next bar in strategy; BrokerSim uses only past/current bars for fills; random seeds fixed if any randomness. Knows BacktestEngineV1 and BrokerSim entry points.
- **How:** Skill with checklist + optional grep/read for common lookahead patterns (e.g. `bars[i+1]`, `df.shift(-1)`).
- **When:** “Review backtest code”, “Add new strategy”, or when editing `engine/solat_engine/backtest/` or `strategies/`.
- **Input:** Strategy or backtest loop code. **Output:** Pass/fail + list of lookahead or non-determinism risks.

### 3.3 Strategy (Elite 8) Agent
- **Implemented:** `.cursor/skills/solat-strategy-elite8/SKILL.md`.
- **Why:** Elite 8 strategies share BarData, SignalIntent, warmup, and indicator usage; new strategies must plug in consistently.
- **What:** Knows Elite8BaseStrategy, BarData, generate_signal(bars, current_position), reason codes, indicators (EMA, RSI, MACD, ATR, Ichimoku, etc.). Suggests: use BarData; return SignalIntent; no lookahead; use shared indicators; add reason codes. Points to `strategies/elite8.py` and `strategies/indicators.py`.
- **How:** Skill for “add or modify Elite 8 strategy” with template and checklist.
- **When:** “Add a strategy”, “How do I add a new Elite 8 bot?”, or editing `strategies/elite8.py` / `strategies/indicators.py`.
- **Input:** Strategy name or desired behaviour. **Output:** Class skeleton, indicator usage, and integration steps.

### 3.4 Execution & Risk Agent
- **Implemented:** `.cursor/rules/solat-execution-risk.mdc`.
- **Why:** Execution (router, risk, kill switch, reconciliation) is safety-critical; changes must respect limits and audit.
- **What:** Knows risk_engine (exposure, daily loss, trades/hour, per-symbol cap), kill_switch, reconciliation, ledger; requires: no bypass of risk checks; all orders go through router; kill switch respected; no silent failure. Reminds: REQUIRE_SL, CLOSE_ON_KILL_SWITCH, REQUIRE_ARM_CONFIRMATION.
- **How:** Rule or skill for `engine/solat_engine/execution/**`. Checklist: risk gating, kill switch, logging.
- **When:** Editing execution/, adding new order types or risk rules.
- **Input:** Diff or new execution path. **Output:** Risk/kill-switch/reconciliation impact and suggestions.

### 3.5 IG Broker Agent
- **Implemented:** `.cursor/rules/solat-ig-broker.mdc`.
- **Why:** IG client has auth, rate limits, version headers, and error handling; changes must not break session or violate rate limits.
- **What:** Knows AsyncIGClient, CST/X-SECURITY-TOKEN, rate limiter, retries, demo vs live URLs; reminds: use rate_limit, redact in logs, handle IGAuthError/IGRateLimitError/IGAPIError; never log credentials.
- **How:** Rule for `engine/solat_engine/broker/ig/**`. Optional skill “add new IG endpoint” with header versions and error mapping.
- **When:** Editing broker/ig/, adding new API calls.
- **Input:** New endpoint or change. **Output:** Correct headers, error handling, and redaction.

### 3.6 Data Layer Agent
- **Implemented:** `.cursor/rules/solat-data-layer.mdc`.
- **Why:** Parquet, aggregation, quality, and IG history must stay consistent (timeframes, schemas, no accidental overwrites).
- **What:** Knows ParquetStore, HistoricalBar, SupportedTimeframe, aggregate, quality checks, ig_history; enforces: use HistoricalBar/SupportedTimeframe; write through store; run quality where appropriate; use data_dir from config.
- **How:** Rule for `engine/solat_engine/data/**`. Skill for “add new timeframe or symbol sync”.
- **When:** Editing data/, adding aggregation or new data sources.
- **Input:** Data flow or new script. **Output:** Correct models and store usage.

### 3.7 Market Data Agent
- **Implemented:** `.cursor/rules/solat-market-data.mdc`.
- **Why:** Bar builder, streaming, polling, and publisher feed into strategies and UI; ordering and staleness matter.
- **What:** Knows bar_builder, streaming, polling, publisher, EventType (QUOTE_RECEIVED, BAR_RECEIVED); reminds: no lookahead in bar building; staleness threshold; persist bars flag; event bus usage.
- **How:** Rule for `engine/solat_engine/market_data/**`.
- **When:** Editing market_data/ or adding new feeds.
- **Input:** Change description. **Output:** Consistency with event bus and data flow.

---

## 4. API & Integration Agents

### 4.1 Engine API Surface Agent
- **Implemented:** `.cursor/rules/solat-engine-api-surface.mdc`.
- **Why:** REST and WebSocket contracts must stay consistent for the desktop client; breaking changes cause runtime errors.
- **What:** Knows routes: /health, /config, /ws; backtest, catalog, chart, data, execution, ig, market_data. Response shapes (HealthResponse, ConfigResponse, backtest result, etc.). WS message types (heartbeat, sync_*, backtest_*, execution_*, quote_received, etc.). Suggests: version or extend, don’t remove fields without deprecation.
- **How:** Skill or rule when editing `engine/solat_engine/api/**` or `main.py`. Optional: small “API contract” snippet per router.
- **When:** “Add endpoint”, “Change response of /X”, or editing api/ or main.py.
- **Input:** Route or message type. **Output:** Current contract and migration or extension suggestion.

### 4.2 Desktop–Engine Contract Agent
- **Implemented:** `.cursor/skills/solat-desktop-engine-contract/SKILL.md`.
- **Why:** UI calls engine HTTP/WS; mismatched URLs, payloads, or message types cause silent failures.
- **What:** Knows desktop hooks (useEngineHealth, useWebSocket, useExecutionStatus) and what they call; engine base URL (env/config); WS message handling. Ensures: any new UI feature that needs engine data uses correct endpoint and payload; any new engine event that UI should show is documented and consumed.
- **How:** Skill: “Adding UI feature that needs engine data” → list endpoints/WS events and hook usage.
- **When:** “Add UI for X”, “Engine now sends Y; how does UI subscribe?”, or editing hooks vs api.
- **Input:** Feature (e.g. “backtest progress”). **Output:** Endpoint/WS event + hook changes.

---

## 5. Security & Safety Agents

### 5.1 Secrets & Credentials Agent
- **Implemented:** `.cursor/rules/solat-secrets-credentials.mdc`.
- **Why:** SECURITY.md: no credentials in repo, logs, or error messages; env only; redaction for any sensitive field.
- **What:** Detects: hardcoded API keys, passwords, tokens; logging of request/response with auth headers; credentials in error messages. Suggests: use env/SecretStr; use redact_sensitive(); log “configured: bool” not value. Knows .env.example and SOLAT_/IG_ vars.
- **How:** Always-on or file rule; can run on diff. Pattern list: api_key, password, secret, token, authorization, IG_.
- **When:** Every commit or when editing config, broker, or any code touching credentials.
- **Input:** Diff or file. **Output:** “Possible secret exposure” + fix (env + redaction).

### 5.2 Security Checklist Agent
- **Implemented:** `.cursor/skills/solat-security-checklist/SKILL.md`.
- **Why:** SOLAT has specific security requirements: localhost-only, CSP, demo-first, kill switch tested.
- **What:** Checklist: engine binds 127.0.0.1; no 0.0.0.0; CSP allows only self + engine origin; no disabling TLS for IG; kill switch path exists and is testable; no credentials in frontend.
- **How:** Skill run before “security-sensitive” changes or on demand. References SECURITY.md.
- **When:** “Security review”, “Prepare for live”, or when touching main.py, Tauri config, or execution.
- **Input:** Scope (e.g. “engine” or “desktop”). **Output:** Checklist with pass/fail and references.

### 5.3 Logging & Audit Agent
- **Implemented:** `.cursor/rules/solat-logging-audit.mdc`.
- **Why:** Trading and execution must be auditable; logs must never contain secrets.
- **What:** Enforces: get_logger(__name__); structured extra={}; no f-strings with secrets; redact_sensitive for request/response; trade/order/fill logged with ids and context. Knows trades.log and run artefact layout.
- **How:** Rule for engine (and optionally desktop). Pattern: warn on logger.*(f"...", *with_secret).
- **When:** Adding or changing logging in engine or execution.
- **Input:** Logging code. **Output:** Structured alternative and redaction reminder.

---

## 6. Testing Agents

### 6.1 Engine Test Agent
- **Implemented:** `.cursor/skills/solat-engine-test/SKILL.md`.
- **Why:** CONVENTIONS: pytest, test_<module>.py, fixtures, >80% on core logic; async with pytest-asyncio.
- **What:** Suggests test file location and name; fixture patterns (e.g. parquet_store, sample bars); use respx/httpx for API mocking; async tests with pytest-asyncio. Knows engine/tests/ and conftest.
- **How:** Skill “write test for X” with template. Rule when adding engine code: “add or update test”.
- **When:** “Add test for X”, “How do I test IG client?”, or after adding engine feature.
- **Input:** Module or function. **Output:** Test file path, fixture sketch, and example test.

### 6.2 API Contract Test Agent
- **Implemented:** `.cursor/skills/solat-api-contract-test/SKILL.md`.
- **Why:** REST and WS contracts should have explicit tests so regressions are caught.
- **What:** Knows existing test_backtest_endpoints, test_health, test_ig_endpoints, etc.; pattern: status codes, response shape, error cases. Suggests: test 200 + body schema; test 401/422 where applicable; test WS message types.
- **How:** Skill when adding or changing API route. Template: request → expected status + body.
- **When:** “Add test for new endpoint” or editing api/.
- **Input:** Route and method. **Output:** Test cases (status + body/WS).

### 6.3 Backtest Golden / Regression Agent
- **Implemented:** `.cursor/skills/solat-backtest-regression/SKILL.md`.
- **Why:** Backtest results must be reproducible; changing strategy or fill model should be caught by known-good outputs.
- **What:** Knows backtest artefacts (metrics.json, equity.parquet, etc.); suggests: small golden dataset, run backtest, snapshot metrics; regression test compares new run to snapshot. Optional: parameterise symbol/timeframe/strategy.
- **How:** Skill “add backtest regression test” with dataset + run + assert metrics within tolerance.
- **When:** “Lock backtest results”, “Add regression test for strategy X”.
- **Input:** Strategy + symbol + timeframe. **Output:** Test script and snapshot location.

---

## 7. Documentation Agents

### 7.1 Docs Update Agent
- **Implemented:** `.cursor/skills/solat-docs-update/SKILL.md`.
- **Why:** ARCHITECTURE, ROADMAP, CONVENTIONS, SECURITY must reflect code; stale docs mislead humans and AI.
- **What:** When code structure or behaviour changes: suggest doc updates. E.g. new route → ARCHITECTURE “REST API”; new execution path → SECURITY or ARCHITECTURE data flow; phase completed → ROADMAP tick.
- **How:** Rule or skill: “After changing X, consider updating Y.” Optional: when saving ROADMAP.md, cross-check with engine/ and api/.
- **When:** After significant engine or API change; or when user asks “update docs”.
- **Input:** Summary of code change. **Output:** List of doc files and suggested edits.

### 7.2 README & Onboarding Agent
- **Implemented:** `.cursor/rules/solat-readme-onboarding.mdc` + `.cursor/skills/solat-readme-onboarding/SKILL.md`.
- **Why:** README and quickstart must work (commands, env, ports) so new devs and Cursor don’t guess.
- **What:** Keeps README in sync: prerequisites (Python 3.11+, uv, Node 18+, pnpm, Rust); copy .env.example; ./scripts/dev.sh; ports 8765 (engine), 1420 (Tauri dev); where to find ARCHITECTURE, CONVENTIONS, SECURITY, ROADMAP.
- **How:** Rule when editing README or .env.example. Skill “onboard new dev” → ordered steps.
- **When:** Editing README, adding env vars, or “how do I run this?”
- **Input:** Change or question. **Output:** README snippet or onboarding steps.

### 7.3 Inline Comment & JSDoc Agent
- **Implemented:** `.cursor/rules/solat-inline-comment-jsdoc.mdc`.
- **Why:** CONVENTIONS and .cursorrules: file header (file name, purpose), JSDoc for exported functions, comments above non-obvious logic.
- **What:** Ensures: top-of-file “File: X / Purpose: Y”; exported functions have JSDoc (params, returns); complex blocks have one-line comment. Python: docstrings; TypeScript: JSDoc.
- **How:** Rule for engine and apps/desktop; optionally run on new files.
- **When:** Creating new file or “add docs to this function”.
- **Input:** File or function. **Output:** Filled-in header and JSDoc.

---

## 8. DevOps & CI Agents

### 8.1 CI Pipeline Agent
- **Implemented:** `.cursor/rules/solat-ci-pipeline.mdc` + `.cursor/skills/solat-ci-pipeline/SKILL.md`.
- **Why:** CI runs engine tests, UI typecheck, Tauri build; changes to structure or commands must not break CI.
- **What:** Knows .github/workflows/ci.yml: uv, pnpm, ruff, mypy, pytest, typecheck, tauri build; matrix currently macos-latest. Suggests: add Windows/Linux when ready; keep commands in sync with package.json and pyproject.toml.
- **How:** Rule when editing ci.yml, package.json, or pyproject.toml. Skill “add CI step for X”.
- **When:** “Add CI job”, “Fix CI”, or editing workflows or root scripts.
- **Input:** Desired check or platform. **Output:** YAML snippet or command alignment.

### 8.2 Environment & Config Agent
- **Implemented:** `.cursor/rules/solat-environment-config.mdc` + `.cursor/skills/solat-environment-config/SKILL.md`.
- **Why:** .env.example must list every env var used; SOLAT_ prefix; no default secrets.
- **What:** Cross-references config.py (and any other config consumers) with .env.example; suggests new vars for new settings; reminds: document in README or CONVENTIONS if non-obvious.
- **How:** Rule when adding config or env. Skill “add new setting” → config field + .env.example line + doc note.
- **When:** Adding Settings field or new env var.
- **Input:** Setting name and type. **Output:** config.py snippet, .env.example line, and doc pointer.

### 8.3 Build & Package Agent
- **Implemented:** `.cursor/rules/solat-build-package.mdc` + `.cursor/skills/solat-build-package/SKILL.md`.
- **Why:** Tauri build and engine install must work from clean clone; pnpm workspace and uv project layout matter.
- **What:** Knows: pnpm-workspace (apps/*), engine pyproject.toml and uv; desktop build (tsc + vite); Tauri build path apps/desktop. Suggests: correct filter for pnpm; engine deps in pyproject.toml; no hardcoded paths.
- **How:** Rule when editing package.json, pyproject.toml, or Tauri config. Skill “add new app or package”.
- **When:** “Build fails”, “Add dependency”, or changing workspace layout.
- **Input:** Error or desired change. **Output:** Fix or layout suggestion.

---

## 9. Tauri & Desktop-Specific Agents

### 9.1 Tauri Config & Permissions Agent
- **Implemented:** `.cursor/rules/solat-tauri-config.mdc`.
- **Why:** Tauri capabilities and CSP control what the app can do; wrong config can break features or security.
- **What:** Knows src-tauri/capabilities, tauri.conf.json, CSP; reminds: allow only required permissions; CSP connect-src to engine only; no broad fs or shell unless justified.
- **How:** Rule for apps/desktop/src-tauri/**.
- **When:** Editing Tauri config or adding native feature.
- **Input:** Desired capability. **Output:** Minimal permission and CSP update.

### 9.2 Rust (Tauri Backend) Agent
- **Implemented:** `.cursor/rules/solat-rust-tauri.mdc`.
- **Why:** Any Rust in src-tauri must compile and follow Rust idioms; invoke handlers must match frontend calls.
- **What:** Knows Tauri invoke pattern; Rust style; that most logic lives in Python engine so Rust stays thin. Suggests: keep Rust layer minimal; document any new command in frontend.
- **How:** Rule for apps/desktop/src-tauri/**/*.rs.
- **When:** Editing Rust or adding Tauri command.
- **Input:** Command or Rust snippet. **Output:** Correct invoke/handler and docs.

---

## 10. Run Artefacts & Data Agents

### 10.1 Run ID & Artefact Layout Agent
- **Implemented:** `.cursor/rules/solat-run-id-artefacts.mdc`.
- **Why:** CONVENTIONS define run_id format and data/runs/{run_id}/ layout; tools and humans depend on it.
- **What:** Enforces: run_id = {type}_{date}_{time}_{uuid8}; type = backtest | paper | live; directory layout (config.json, signals.parquet, orders.parquet, fills.parquet, equity.parquet, metrics.json, logs/). Suggests: use runtime.artefacts or equivalent; don’t invent new top-level files without doc update.
- **How:** Rule for code that writes under data/runs/ or generates run_id.
- **When:** “Where do backtest results go?”, or editing runtime/artefacts or run_context.
- **Input:** Run type. **Output:** run_id format and directory layout.

### 10.2 Metrics JSON Schema Agent
- **Implemented:** `.cursor/rules/solat-metrics-json-schema.mdc`.
- **Why:** metrics.json is consumed by UI or analytics; changing shape breaks consumers.
- **What:** Knows CONVENTIONS metrics structure (run_id, strategy_id, symbol, timeframe, dates, capital, return_pct, drawdown, sharpe, trades, win_rate, profit_factor). Suggests: add new fields in backward-compatible way; document in CONVENTIONS if extending.
- **How:** Rule or skill when changing backtest metrics or metrics.json writer.
- **When:** Editing backtest metrics or metrics export.
- **Input:** New metric or change. **Output:** Schema-compliant addition.

---

## 11. Meta & Workflow Agents

### 11.1 PR / Change Review Agent
- **Implemented:** `.cursor/skills/solat-pr-review/SKILL.md`.
- **Why:** Every PR should respect conventions, security, and tests; one agent can run a lightweight “pre-PR” checklist.
- **What:** Runs: conventions (Python/TS) on changed files; secrets check on diff; “did you add tests?” for engine/api changes; “did you update docs?” for behaviour changes; ROADMAP tick if phase deliverable completed.
- **How:** Skill “review my changes” with checklist; optionally reads diff and suggests.
- **When:** “Review this PR”, “Check my changes”, or before pushing.
- **Input:** Diff or list of files. **Output:** Checklist results and concrete suggestions.

### 11.2 “What Broke?” Debug Agent
- **Implemented:** `.cursor/skills/solat-what-broke/SKILL.md`.
- **Why:** Failures can be engine vs UI vs env vs IG; narrowing scope saves time.
- **What:** Asks or infers: failing command (dev.sh vs dev:engine vs dev:ui); error message; recent changes. Maps: “connection refused 8765” → engine not running; “401 from IG” → credentials/session; “WS disconnect” → engine crash or CORS; “build failed” → dependency or Tauri/Rust. Suggests: run engine alone; check .env; check IG_*; read engine log.
- **How:** Skill with decision tree and common errors.
- **When:** “It doesn’t work”, “Connection failed”, “Build failed”.
- **Input:** Error message and last action. **Output:** Likely cause and next steps.

### 11.3 Dependency Upgrade Agent
- **Implemented:** `.cursor/skills/solat-dependency-upgrade/SKILL.md`.
- **Why:** Upgrading Python or JS deps can break types or behaviour; an agent can suggest order and test focus.
- **What:** Knows pyproject.toml and package.json; suggests: upgrade one layer at a time (e.g. FastAPI then httpx); run full test suite and typecheck after; check CHANGELOG for breaking changes; pin versions in lockfile.
- **How:** Skill “upgrade dependency X” with steps and test commands.
- **When:** “Upgrade FastAPI”, “Upgrade React”, or “Update deps”.
- **Input:** Package name or “all”. **Output:** Order of operations and verification steps.

### 11.4 Agent Author (Self-Prompt) Agent
- **Implemented:** `.cursor/skills/solat-agent-author/SKILL.md`.
- **Why:** Ensures new Cursor rules/skills follow the same prompt-engineering and structure (see AGENT-AUTHOR-PROMPT.md).
- **What:** When creating or editing a rule/skill: apply AGENT-AUTHOR-PROMPT (trigger, I/O, examples, concise, strict to project). Validates: description (WHAT + WHEN), frontmatter, one concern per rule, skill under ~500 lines with progressive disclosure.
- **How:** Rule or skill that wraps creation of .mdc or SKILL.md; references docs/AGENT-AUTHOR-PROMPT.md.
- **When:** “Create a Cursor rule for X”, “Write a skill for Y”.
- **Input:** Agent purpose and scope. **Output:** Draft rule/skill that follows the self-prompt.

---

## 12. Summary Table

| # | Agent | Type | File | When | Primary output |
|---|--------|------|------|------|-----------------|
| 1.1 | Project Context | Rule (always) | `.cursor/rules/solat-project-context.mdc` | Every session | Context injection |
| 1.2 | ROADMAP & Phase | Skill | `.cursor/skills/solat-roadmap-phase/SKILL.md` | “What’s next”, ROADMAP edit | Phase status, next tasks, build_log update |
| 1.3 | Architecture Navigator | Skill | `.cursor/skills/solat-architecture-navigator/SKILL.md` | “Where is X?” | Paths + roles |
| 2.1 | Python Conventions | Rule (globs) | `.cursor/rules/solat-python-conventions.mdc` | engine/**/*.py | Compliant code |
| 2.2 | TS/React Conventions | Rule (globs) | `.cursor/rules/solat-ts-react-conventions.mdc` | apps/desktop/src/** | Compliant code |
| 2.3 | Naming & File Layout | Rule | `.cursor/rules/solat-naming-layout.mdc` | New/rename files | Names + layout |
| 2.4 | Git & Commit | Skill | `.cursor/skills/solat-git-commit/SKILL.md` | Commit time | Conventional commit msg |
| 3.1 | Domain Model | Rule | `.cursor/rules/solat-domain-model.mdc` | domain/ or domain usage | Types + Decimal |
| 3.2 | Backtest Integrity | Skill | `.cursor/skills/solat-backtest-integrity/SKILL.md` | Backtest/strategy changes | Lookahead/determinism check |
| 3.3 | Strategy (Elite 8) | Skill | `.cursor/skills/solat-strategy-elite8/SKILL.md` | New strategy | Skeleton + checklist |
| 3.4 | Execution & Risk | Rule | `.cursor/rules/solat-execution-risk.mdc` | execution/ | Risk/kill-switch impact |
| 3.5 | IG Broker | Rule | `.cursor/rules/solat-ig-broker.mdc` | broker/ig/ | Headers, errors, redaction |
| 3.6 | Data Layer | Rule | `.cursor/rules/solat-data-layer.mdc` | data/ | Store + models usage |
| 3.7 | Market Data | Rule | `.cursor/rules/solat-market-data.mdc` | market_data/ | Event bus + flow |
| 4.1 | Engine API Surface | Rule | `.cursor/rules/solat-engine-api-surface.mdc` | api/ or main | Contract + migration |
| 4.2 | Desktop–Engine Contract | Skill | `.cursor/skills/solat-desktop-engine-contract/SKILL.md` | New UI/engine feature | Endpoints + hooks |
| 5.1 | Secrets & Credentials | Rule | `.cursor/rules/solat-secrets-credentials.mdc` | Any code | Exposure fix |
| 5.2 | Security Checklist | Skill | `.cursor/skills/solat-security-checklist/SKILL.md` | Security review | Checklist result |
| 5.3 | Logging & Audit | Rule | `.cursor/rules/solat-logging-audit.mdc` | Logging code | Structured + redaction |
| 6.1 | Engine Test | Skill | `.cursor/skills/solat-engine-test/SKILL.md` | New engine code | Test path + template |
| 6.2 | API Contract Test | Skill | `.cursor/skills/solat-api-contract-test/SKILL.md` | New/changed route | Test cases |
| 6.3 | Backtest Regression | Skill | `.cursor/skills/solat-backtest-regression/SKILL.md` | Lock backtest | Regression test |
| 7.1 | Docs Update | Skill | `.cursor/skills/solat-docs-update/SKILL.md` | After code change | Doc edit list |
| 7.2 | README & Onboarding | Rule + Skill | `.cursor/rules/solat-readme-onboarding.mdc`, `.cursor/skills/solat-readme-onboarding/SKILL.md` | README/env | Steps + snippet |
| 7.3 | Inline Comment & JSDoc | Rule | `.cursor/rules/solat-inline-comment-jsdoc.mdc` | New/edited code | Headers + JSDoc |
| 8.1 | CI Pipeline | Rule + Skill | `.cursor/rules/solat-ci-pipeline.mdc`, `.cursor/skills/solat-ci-pipeline/SKILL.md` | ci.yml / scripts | CI alignment |
| 8.2 | Environment & Config | Rule + Skill | `.cursor/rules/solat-environment-config.mdc`, `.cursor/skills/solat-environment-config/SKILL.md` | New setting | config + .env.example |
| 8.3 | Build & Package | Rule + Skill | `.cursor/rules/solat-build-package.mdc`, `.cursor/skills/solat-build-package/SKILL.md` | Build/deps | Fix or layout |
| 9.1 | Tauri Config | Rule | `.cursor/rules/solat-tauri-config.mdc` | src-tauri | Permissions + CSP |
| 9.2 | Rust (Tauri) | Rule | `.cursor/rules/solat-rust-tauri.mdc` | *.rs in desktop | Invoke + minimal Rust |
| 10.1 | Run ID & Artefacts | Rule | `.cursor/rules/solat-run-id-artefacts.mdc` | data/runs/ code | run_id + layout |
| 10.2 | Metrics JSON Schema | Rule | `.cursor/rules/solat-metrics-json-schema.mdc` | Metrics export | Schema compliance |
| 11.1 | PR / Change Review | Skill | `.cursor/skills/solat-pr-review/SKILL.md` | Pre-PR | Checklist + suggestions |
| 11.2 | “What Broke?” Debug | Skill | `.cursor/skills/solat-what-broke/SKILL.md` | Failures | Cause + steps |
| 11.3 | Dependency Upgrade | Skill | `.cursor/skills/solat-dependency-upgrade/SKILL.md` | Upgrade request | Order + verify |
| 11.4 | Agent Author | Skill | `.cursor/skills/solat-agent-author/SKILL.md` | New rule/skill | Draft agent |

---

## 13. Suggested Implementation Order

1. **Always-on:** Project Context (1.1), Secrets (5.1), Python Conventions (2.1), TS Conventions (2.2).
2. **High value, file-scoped:** Domain Model (3.1), Execution & Risk (3.4), IG Broker (3.5), Engine API (4.1), Logging (5.3).
3. **On-demand skills:** ROADMAP & Phase (1.2), Architecture Navigator (1.3), Backtest Integrity (3.2), Strategy Elite 8 (3.3), Security Checklist (5.2), Engine Test (6.1), PR Review (11.1), “What Broke?” (11.2).
4. **When touching area:** Data Layer (3.6), Market Data (3.7), Desktop–Engine Contract (4.2), Run ID/Artefacts (10.1), Tauri Config (9.1), CI (8.1), Docs Update (7.1).
5. **Nice-to-have:** Git Commit (2.4), Naming (2.3), API Contract Test (6.2), Backtest Regression (6.3), README (7.2), Inline Comment (7.3), Env & Config (8.2), Build & Package (8.3), Rust (9.2), Metrics Schema (10.2), Dependency Upgrade (11.3), Agent Author (11.4).

Use this inventory to create Cursor rules (`.cursor/rules/*.mdc`) and skills (`.cursor/skills/<name>/SKILL.md`) following `docs/AGENT-AUTHOR-PROMPT.md`.
