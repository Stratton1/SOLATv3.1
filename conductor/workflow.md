# Development Workflow

## Version Control
- **Git Flow:** Modified Git Flow (main, develop, feature branches).
- **Branch Naming:**
    - `feature/<name>`: New features
    - `fix/<name>`: Bug fixes
    - `release/<version>`: Release preparation
- **Commit Messages:** Conventional Commits (`feat(scope): ...`, `fix(scope): ...`).

## Development Cycle
1.  **Create Branch:** `git checkout -b feature/my-feature`
2.  **Develop:** Write code following project conventions.
3.  **Test:**
    - Engine: `pnpm test:engine`
    - UI: `pnpm test:ui`
4.  **Lint/Format:**
    - Engine: `pnpm lint:engine`, `pnpm format:engine`
    - UI: `pnpm lint:ui`
5.  **Commit:** `git commit -m "feat(scope): description"`
6.  **Pull Request:** Open PR against `develop` (or `main` if hotfix).

## Release Process
- Use `scripts/bump_version.py` to synchronize versions.
- Build commands: `pnpm build:all` or specific scope.
