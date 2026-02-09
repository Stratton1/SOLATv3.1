---
name: solat-agent-author
description: Applies AGENT-AUTHOR-PROMPT when creating or editing Cursor rules/skills. Use when creating a Cursor rule for X or writing a skill for Y. Outputs draft rule/skill that follows the self-prompt.
---

# SOLAT Agent Author (Self-Prompt) Agent (11.4)

When the user says **"Create a Cursor rule for X"** or **"Write a skill for Y"**, apply [docs/AGENTS/AGENT-AUTHOR-PROMPT.md](docs/AGENTS/AGENT-AUTHOR-PROMPT.md) and output a **draft rule or skill** that follows the self-prompt. Validate: description (WHAT + WHEN), frontmatter, one concern per rule, skill under ~500 lines with progressive disclosure.

## Input

- **Agent purpose and scope:** What the agent does (single objective); when it triggers (user phrasing, file type); where it applies (always / globs / dirs).
- **Type:** Rule (.mdc) or Skill (SKILL.md in .cursor/skills/<name>/).

## Rules (from AGENT-AUTHOR-PROMPT)

### Before creating

1. **Clarify intent:** What should the agent do? Who triggers it? Where does it apply?
2. **Gather constraints:** Project conventions (CONVENTIONS, ROADMAP); existing rules/skills; line limits, third-person description.
3. **Define success:** One-sentence success criterion; optional input → output example.

### Input/Output (mandatory)

- **Trigger:** When applied (alwaysApply or globs for rules; "Use when…" in skill description).
- **Context assumed:** What the agent has (open file, selection, repo root).
- **User intent signals:** Example phrases ("review this PR", "write commit message").
- **Output format:** Structure of response (list, template, checklist); scope; constraints.
- **Examples:** At least one input → output pair (for skills: Example 1 / Example 2).

### Quality

- **Clarity:** Imperative instructions; one instruction per step; no vague "could/might" unless optional.
- **Structure:** Frontmatter first (description, globs, alwaysApply for rules; name, description for skills); sections: Purpose → Trigger → Steps → Examples → References.
- **Efficiency:** No redundant explanation; default + escape hatch; consistent terminology; rules under ~50 lines where possible; skills under ~500 lines with progressive disclosure (link to reference.md if needed).
- **Strictness:** Align to project (CONVENTIONS, ROADMAP, SECURITY) and Cursor conventions (frontmatter, description in third person, WHAT + WHEN in description).

## Validation checklist

- [ ] Description is specific and includes trigger terms (WHAT + WHEN).
- [ ] Description is in third person.
- [ ] Rule: frontmatter has description and globs or alwaysApply.
- [ ] Skill: frontmatter has name and description; SKILL.md under ~500 lines or uses progressive disclosure.
- [ ] At least one input → output example.
- [ ] No time-sensitive absolutes; no Windows paths; consistent terminology.

## Output

1. **Draft rule or skill:** Full content for .cursor/rules/<name>.mdc or .cursor/skills/<name>/SKILL.md.
2. **Path:** Exact file path.
3. **Optional:** One-line "Test: …" (how to verify the agent triggers and behaves).

Reference: [docs/AGENTS/AGENT-AUTHOR-PROMPT.md](docs/AGENTS/AGENT-AUTHOR-PROMPT.md), [docs/AGENTS/AGENTS-INVENTORY.md](docs/AGENTS/AGENTS-INVENTORY.md).
