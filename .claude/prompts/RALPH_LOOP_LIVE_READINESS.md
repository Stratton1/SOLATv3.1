# SOLAT v3.1 - Ralph Loop: Live Readiness

## Prompt

```
You are an expert software engineer and trading systems architect. Your task is to systematically prepare the SOLAT v3.1 algorithmic trading system for LIVE production deployment with the IG broker API.

## CONTEXT

<codebase_context>
{{READ: .claude/prompts/CODEBASE_CONTEXT.md}}
</codebase_context>

<quality_criteria>
{{READ: .claude/prompts/QUALITY_CRITERIA.md}}
</quality_criteria>

<roadmap>
{{READ: LIVE_READINESS_ROADMAP.md}}
</roadmap>

## CURRENT STATE

- Historical Data: 37 instruments, 1.5GB (2020-2025) ✅
- IG LIVE Login: Working (Account WVK88) ✅
- Test Suite: BROKEN (43 errors, 14 failures) ❌
- IG Epic Mapping: Partial (3/10 FX pairs) ⚠️
- Walk-Forward: Bug fixed, untested ⚠️
- Paper Trading: Not started ❌
- Risk Controls: Not audited ❌

## RALPH LOOP PROTOCOL

You will execute an iterative improvement loop for each phase. For EACH phase:

### Step 1: ASSESS
Analyze the current state against exit criteria. Ask yourself:
- What specific criteria are not yet met?
- What is the minimal change needed to meet them?
- What are the risks of this change?

### Step 2: PLAN
Create a focused action plan:
- List 1-5 specific tasks
- Order by dependency (what must come first?)
- Estimate complexity (trivial/moderate/complex)

### Step 3: EXECUTE
Implement the changes:
- Make ONE logical change at a time
- After each change, validate it worked
- If validation fails, diagnose before continuing

### Step 4: VALIDATE
Run validation commands from QUALITY_CRITERIA.md:
- Execute the exact commands specified
- Parse the output for pass/fail signals
- Record the results

### Step 5: EVALUATE
Determine next action:
- ✅ ALL CRITERIA MET → Proceed to next phase
- ⚠️ PARTIAL PROGRESS → Return to Step 1 with updated state
- ❌ BLOCKED → Report blocker and request user input
- 🔄 MAX ITERATIONS (5) → Report status and request guidance

## PHASE EXECUTION ORDER

Execute phases in this exact order. Do NOT skip phases.

### PHASE 1: Test Suite (PRIORITY: CRITICAL)
Goal: All tests pass with new DI pattern

Tasks:
1. Create `tests/conftest.py` with shared fixtures using `app.dependency_overrides`
2. Migrate test files one by one
3. Run `pytest --tb=short` after each migration
4. Fix any new failures before proceeding

Exit: `pytest` returns 0 errors, 0 failures

### PHASE 2: IG LIVE Epic Mapping (PRIORITY: HIGH)
Goal: All instruments have correct LIVE epics

Tasks:
1. Research IG epic patterns for remaining instruments
2. Add `live_epic` to all CatalogueSeedItem entries in seed.py
3. Update catalog service to use live_epic when IG_ACC_TYPE=LIVE
4. Test with actual LIVE API calls

Exit: All 10 FX pairs return valid quotes on LIVE

### PHASE 3: Data Quality (PRIORITY: MEDIUM)
Goal: Validate imported historical data

Tasks:
1. Run check_data_quality.py
2. Fix any OHLC validation errors
3. Document any acceptable gaps (weekends)

Exit: 37/37 instruments pass quality check

### PHASE 4: Backtest Suite (PRIORITY: HIGH)
Goal: Verify backtesting works with new data

Tasks:
1. Start engine
2. Run single bot backtest
3. Run all 8 bots
4. Run Grand Sweep
5. Identify top performers

Exit: At least 2 bots with Sharpe > 1.0

### PHASE 5: Walk-Forward (PRIORITY: MEDIUM)
Goal: Validate out-of-sample performance

Tasks:
1. Configure walk-forward parameters
2. Run on top 3 bot/symbol combos
3. Analyze OOS degradation
4. Select final candidates for LIVE

Exit: OOS Sharpe > 60% of IS Sharpe for at least 1 combo

### PHASE 6: Paper Trading (PRIORITY: HIGH)
Goal: Validate real-time operation

Tasks:
1. Configure PAPER mode with LIVE data
2. Run for 24-48 hours
3. Monitor WebSocket events
4. Verify signal generation

Exit: 24h stable operation

### PHASE 7: Risk Controls (PRIORITY: CRITICAL)
Goal: Ensure safety mechanisms work

Tasks:
1. Audit kill switch
2. Test daily loss limit
3. Test position limits
4. Document reset procedure

Exit: Kill switch tested and working

### PHASE 8: Go-Live (PRIORITY: CRITICAL)
Goal: Final checklist and first trade

Tasks:
1. Verify all phases complete
2. Set minimum position sizes
3. Monitor first trade
4. Document any issues

Exit: First LIVE trade executed safely

## OUTPUT FORMAT

For each phase, output in this format:

```
═══════════════════════════════════════════════════════════════
PHASE {N}: {NAME}
═══════════════════════════════════════════════════════════════

## ITERATION {I}

### ASSESS
- Criteria Met: {list}
- Criteria Remaining: {list}
- Current Blockers: {list or "None"}

### PLAN
1. {task 1} [{complexity}]
2. {task 2} [{complexity}]
...

### EXECUTE
{Show the actual changes made, code written, commands run}

### VALIDATE
```
{Actual command output}
```
Result: {PASS/FAIL/PARTIAL}

### EVALUATE
{Analysis of results}

**DECISION:** {PROCEED / RETRY / BLOCKED / MAX_ITERATIONS}

---
```

## CONSTRAINTS

1. **Safety First**: Never execute trades in LIVE mode during testing
2. **Incremental Changes**: One logical change per iteration
3. **Validate Everything**: Run tests after every code change
4. **Document Decisions**: Explain why you chose an approach
5. **Fail Fast**: If blocked, report immediately rather than guessing
6. **Preserve Working Code**: Do not refactor code that isn't broken

## SUCCESS CRITERIA

The Ralph Loop is COMPLETE when:
- All 8 phases show ✅ status
- No ⚠️ or ❌ items remain
- Final Go-Live checklist is signed off
- First LIVE trade documented

## BEGIN

Start with PHASE 1: Test Suite. Assess current state and begin iteration 1.
```

---

## Usage Instructions

### Option A: Single Session (Recommended for Phases 1-4)
Copy the prompt above and paste into a fresh Claude session with the SOLAT codebase loaded.

### Option B: Multi-Session (Recommended for Phases 5-8)
For phases requiring real-time operation:
1. Complete Phases 1-4 in one session
2. Start a new session for Phase 5 (walk-forward)
3. Start a new session for Phase 6 (paper trading - requires 24h)
4. Complete Phases 7-8 in final session

### Option C: Automated (Advanced)
Use Claude Code CLI with the prompt:
```bash
cd /path/to/solat_v3.1
claude --prompt "$(cat .claude/prompts/RALPH_LOOP_LIVE_READINESS.md)"
```

---

## Customization Points

### Adjust Iteration Limits
Change `MAX ITERATIONS (5)` to higher/lower based on complexity.

### Add Phase-Specific Context
Insert additional context between phases if needed:
```
<additional_context>
User discovered that IG LIVE uses different rate limits.
Adjust API calls accordingly.
</additional_context>
```

### Skip Completed Phases
If resuming after partial completion:
```
COMPLETED PHASES: 1, 2, 3
START FROM: PHASE 4
```

---

## Troubleshooting

### Loop Gets Stuck
- Check if external dependency is blocking (API down, credentials expired)
- Review last 3 iterations for patterns
- Request user input with specific question

### Tests Keep Failing
- Focus on ONE test file at a time
- Check for import order issues with DI
- Verify `app.dependency_overrides.clear()` is called in teardown

### Backtest Returns Empty Results
- Verify data exists: `ls data/parquet/bars/instrument_symbol=EURUSD/`
- Check date range overlaps with available data
- Verify symbol mapping matches storage format
