---
name: solat-security-checklist
description: Runs SOLAT security checklist (localhost, CSP, TLS, kill switch, no credentials in frontend). Use for security review, prepare for live, or when touching main.py, Tauri config, or execution.
---

# SOLAT Security Checklist Agent (5.2)

When the user asks for a **security review**, **prepare for live**, or when touching [engine/solat_engine/main.py](engine/solat_engine/main.py), Tauri config, or [engine/solat_engine/execution/](engine/solat_engine/execution/), run this checklist and return **pass/fail** with references.

## Checklist

### Engine

- [ ] **Localhost only:** Engine binds to 127.0.0.1; no 0.0.0.0 or public binding. Check main.py / config (host, port).
- [ ] **No credentials in responses:** /config and any API response do not include API key, password, or tokens; only redacted or boolean (e.g. ig_configured).
- [ ] **Secrets from env:** All IG_* and sensitive config loaded from environment (SecretStr in config.py); no hardcoded secrets.

### Desktop (Tauri)

- [ ] **CSP:** Content-Security-Policy allows only self and engine origin (e.g. connect-src 'self' http://127.0.0.1:8765 ws://127.0.0.1:8765). Check [apps/desktop/src-tauri/tauri.conf.json](apps/desktop/src-tauri/tauri.conf.json) or capabilities.
- [ ] **No credentials in frontend:** UI does not store or send API keys/passwords; all broker access via engine only.
- [ ] **Minimal permissions:** Tauri capabilities grant only required permissions; no broad fs or shell unless justified.

### Broker and TLS

- [ ] **TLS for IG:** All communication with IG uses HTTPS (demo-api.ig.com, api.ig.com); never disable TLS verification.

### Execution and kill switch

- [ ] **Kill switch exists:** Path to activate and reset kill switch (e.g. /execution/kill-switch); documented and testable.
- [ ] **Tested in demo:** Kill switch tested in demo mode before any live use.

## Scope

User may specify **engine** or **desktop** to run only the relevant subset. Otherwise run full checklist.

## Output

1. **Pass / Fail** per item (and overall if requested).
2. **References:** Point to [docs/SECURITY.md](docs/SECURITY.md) and specific files (main.py, config.py, tauri.conf.json, execution routes).
3. **Remediation:** For any fail, one-line fix or doc reference.
