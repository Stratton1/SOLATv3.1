---
name: solat-environment-config
description: Suggests config field, .env.example line, and doc note for a new setting. Use when adding a new env var or config option.
---

# SOLAT Environment & Config Agent (8.2 skill)

When the user says **"Add new setting"** or **"Add env var for X"**, output **config.py snippet**, **.env.example line**, and **doc note** (README or CONVENTIONS if non-obvious).

## Config field (config.py)

- Use Pydantic Field with default, description, and alias if env name differs (e.g. IG_API_KEY).
- Use SecretStr for credentials.
- Use env_prefix SOLAT_ for app settings; use alias for IG_* and other non-prefixed vars.
- Add field_validator for enums or constrained types (e.g. log_level, port range).

## .env.example

- Add line: `VAR_NAME=placeholder_or_default_comment`
- Add brief comment above if not obvious (e.g. "# Max requests per second for IG API").

## Doc note

- If the setting is security-sensitive (ports, credentials, demo/live): ensure README or SECURITY mentions it.
- If it changes run behaviour (data dir, timeouts): mention in README config table or CONVENTIONS.

Output: (1) config.py field snippet, (2) .env.example line(s) with comment, (3) one-line doc pointer.
