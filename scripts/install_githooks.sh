#!/usr/bin/env bash
#
# Install SOLAT git hooks.
#
# Usage: bash scripts/install_githooks.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Configure git to use .githooks directory
git config core.hooksPath .githooks

# Make hooks executable
chmod +x .githooks/pre-commit

echo "Git hooks installed successfully."
echo "  hooks path: .githooks/"
echo "  pre-commit: enforces PROJECT_MEMORY.md / BUILD_LOG.md updates"
echo ""
echo "To skip the hook for a single commit: git commit --no-verify"
