---
name: solat-docs-update
description: Suggests doc updates when code structure or behaviour changes. Use after significant engine/API change or when the user says update docs.
---

# SOLAT Docs Update Agent (7.1)

When the user says **"update docs"** or after a significant engine or API change, output a **list of doc files and suggested edits** so ARCHITECTURE, ROADMAP, CONVENTIONS, and SECURITY stay aligned with code.

## Mapping: code change → doc update

| Code change | Doc to update | Suggested edit |
|-------------|---------------|----------------|
| New REST route or response shape | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Add or update "Communication Protocols" / REST API section; list route and purpose. |
| New WebSocket event type | docs/ARCHITECTURE.md | Add event type and payload to WebSocket section. |
| New execution path or safety gate | [docs/SECURITY.md](docs/SECURITY.md) or ARCHITECTURE | Update data flow or risk/kill-switch description. |
| Phase deliverable completed | [docs/ROADMAP.md](docs/ROADMAP.md) | Tick deliverables that exist in code; update phase overview table if phase is complete. |
| New env var or config | [.env.example](.env.example), [README.md](README.md) or CONVENTIONS | Add var to .env.example; document in README config table or CONVENTIONS if non-obvious. |
| Run artefact or metrics shape change | [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Update Run Artefacts / Metrics JSON Structure. |
| New Cursor agent | [docs/AGENTS/AGENTS-INVENTORY.md](docs/AGENTS/AGENTS-INVENTORY.md) | Add or update agent entry if applicable. |

## Optional: when saving ROADMAP.md

Cross-check [docs/ROADMAP.md](docs/ROADMAP.md) with engine/ and api/: for each phase marked complete, verify deliverables are present in code; suggest ticking or un-ticking boxes.

## Output format

1. **List of doc files** (paths).
2. **Per file:** Short suggested edit (e.g. "Add GET /new-endpoint to REST section", "Tick 'Elite 8 bots implemented' in Phase 040–049").
3. **Optional:** One-sentence rationale per edit.

Do not edit docs by default unless the user asks to apply changes; output suggestions only unless instructed.
