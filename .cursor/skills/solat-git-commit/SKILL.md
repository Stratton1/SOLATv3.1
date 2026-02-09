---
name: solat-git-commit
description: Suggests conventional commit messages from a diff or summary. Use when the user says "commit message", "suggest commit", "write commit message", or runs a commit workflow. Optionally reminds about branch naming (main, develop, feature/*, fix/*).
---

# SOLAT Git & Commit Agent

When the user asks for a **commit message**, **suggest commit**, or **write commit message** (or provides a diff/summary of changes), output one or more **conventional commit** lines. Present tense, imperative mood.

## Format

```
<type>(<scope>): <short description>

[optional body]
```

## Types

- **feat:** New feature
- **fix:** Bug fix
- **docs:** Documentation only
- **test:** Adding or updating tests
- **refactor:** Code change that neither fixes a bug nor adds a feature
- **chore:** Build, tooling, deps, config (no production code)
- **style:** Formatting, whitespace (no logic change)

## Scopes (SOLAT)

Use one of:

- **engine** — Python engine (`engine/solat_engine/`, `engine/tests/`)
- **ui** or **desktop** — Tauri + React (`apps/desktop/`)
- **docs** — Documentation (`docs/`, `README.md`, `BUILD_LOG.md`)
- **ci** — CI/config (`.github/`, root config)
- **agents** — Cursor rules/skills (`.cursor/`, `docs/AGENTS/`)

If changes span multiple areas, use the primary area or the first scope; optionally add a second line for the other.

## Examples

```
feat(engine): add IG broker REST client
fix(desktop): correct WebSocket reconnection logic
docs: update architecture diagram
test(engine): add backtest engine unit tests
chore(ci): add macOS to Tauri build matrix
```

## Branch naming (optional reminder)

When the user is about to commit or create a branch, you may remind:

- **main** — production-ready
- **develop** — integration
- **feature/*** — new features (e.g. `feature/terminal-chart`)
- **fix/*** — bug fixes (e.g. `fix/ws-reconnect`)
- **release/*** — release prep

## Output

1. **One line:** Single conventional commit that summarizes the change.
2. **Multiple lines:** If the user’s summary describes several logical changes, suggest one commit per change (e.g. "feat(engine): X" and "docs: Y").
3. **Body (optional):** If the user wants a body, add a blank line and a short paragraph; otherwise keep it to the subject line.

Do not run git commands. Only output the message text.
