# Product Guidelines

## Core Principles
1.  **Reliability:** The system handles financial transactions; reliability and error handling are paramount.
2.  **Precision:** Use `Decimal` for all financial calculations. Never use floats.
3.  **User Experience:** The desktop UI should provide a professional, responsive experience similar to commercial trading terminals.

## Coding Standards

### Python Engine
- **Style:** Adhere to `ruff` formatting.
- **Typing:** Strict `mypy` compliance.
- **Models:** Pydantic `BaseModel`, immutable where possible.
- **Logging:** Structured logging, no sensitive data.

### TypeScript/React UI
- **Style:** Adhere to `eslint` and `prettier` rules.
- **Components:** Functional components, PascalCase.
- **State:** Encapsulate complex logic in custom hooks.

## Architecture Guidelines
- **Sidecar Pattern:** The UI is a view; the Engine is the source of truth.
- **Communication:** REST for commands/queries, WebSockets for real-time streams.
- **Data Isolation:** Engine handles all heavy data processing and storage (Parquet). UI receives aggregated/view-ready data.
