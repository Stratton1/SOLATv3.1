# PROMPT 016 -- UI/UX Polish & Terminal Usability

## Completed

### A. Animated Splash/Boot Screen
- `SplashScreen.tsx` gates the app until the engine is reachable
- Four boot stages: shell -> engine -> catalogue -> ready
- Polls `/health` every 1.5s with a 20s timeout
- On failure: "Start Engine & Retry", "Retry Connection", "Skip to App"
- Shimmer overlay animation during boot

### B. DevTools Auto-Open Removed
- Removed `window.open_devtools()` from `main.rs` Tauri setup hook
- Users can still open DevTools manually with Cmd+Opt+I (macOS) or F12

### C. InfoTip Component
- Reusable `InfoTip.tsx`: small "i" icon, hover/click popover with explanation
- Deployed on:
  - **StatusScreen**: Engine Health, Trading Mode, Engine Version, Real-time Connection, Execution Control
  - **OptimizationScreen**: Scheduler, Proposals
  - **BlotterScreen**: Trade Blotter header
  - **BacktestsScreen**: Backtest Runs header
  - **SettingsScreen**: Engine, IG Connectivity, Execution Safety, Historical Data

### D. Status Page Jitter Fix
- `useEngineHealth.ts`: `hasDataRef` tracks whether initial fetch succeeded
- `setIsLoading(true)` only fires on initial fetch, not subsequent polls
- On transient errors, stale data stays visible (stale-while-revalidate)
- Cards no longer flash to loading state during 5s poll cycles

### E. Terminal Panel Linking
- Already implemented in Phase 008 workspace system
- Link groups (A, B, C) propagate symbol/timeframe across panels
- **Drawing tools**: Deferred to a future prompt (substantial feature)

### F. Backtests Page
- Already functional: list, view detail, multi-select comparison
- Added InfoTip with explanation of Sharpe, trade count, return
- Improved empty state with step-by-step instructions

### G. Optimise Page (UK Spelling)
- Title: "Optimisation"
- Loading/error text updated to UK spelling
- InfoTips on Scheduler and Proposals sections
- Better empty state explaining how proposals are generated

### H. Blotter Improvements
- CSV export now shows a toast confirmation ("Copied N rows to clipboard")
- Toast auto-dismisses after 2.5 seconds
- Empty states enhanced with descriptive text for Events, Fills, Orders tabs
- InfoTip on Trade Blotter header

### I. This File
- `docs/ux/PROMPT_016_NOTES.md`

## Deferred

| Feature | Reason |
|---------|--------|
| Drawing tools (Terminal) | Major feature; needs separate prompt for crosshair, trendline, fib tools |
| Inline backtest runner | Strategy Drawer in Terminal already handles this flow |
| Per-card independent polling | Current 5s unified poll + stale-while-revalidate is sufficient |

## Files Modified

### New Files
- `apps/desktop/src/components/SplashScreen.tsx`
- `apps/desktop/src/components/InfoTip.tsx`
- `docs/ux/PROMPT_016_NOTES.md`

### Modified Files
- `apps/desktop/src-tauri/src/main.rs` -- engine auto-start, port cleanup, devtools removed
- `apps/desktop/src/App.tsx` -- splash screen gate, /optimise route
- `apps/desktop/src/styles.css` -- splash, infotip, toast, empty state CSS
- `apps/desktop/src/hooks/useEngineHealth.ts` -- stale-while-revalidate jitter fix
- `apps/desktop/src/hooks/useEngineLauncher.ts` -- Tauri invoke wrapper
- `apps/desktop/src/hooks/useWebSocket.ts` -- startup delay, backoff
- `apps/desktop/src/components/StatusScreen.tsx` -- InfoTips, start engine button
- `apps/desktop/src/components/OfflineBanner.tsx` -- start engine button
- `apps/desktop/src/screens/OptimizationScreen.tsx` -- UK spelling, InfoTips, empty states
- `apps/desktop/src/screens/BlotterScreen.tsx` -- CSV toast, InfoTip, empty states
- `apps/desktop/src/screens/BacktestsScreen.tsx` -- InfoTip, empty states
- `apps/desktop/src/screens/SettingsScreen.tsx` -- InfoTips on all sections
