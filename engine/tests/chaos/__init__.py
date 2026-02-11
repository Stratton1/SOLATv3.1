"""
Chaos/failure injection testing suite.

Tests system behavior under adverse conditions:
- Tier 1: Data corruption (disk full, partial writes, stale data)
- Tier 2: State inconsistency (partial fills, reconciliation failures)
- Tier 3: Operational blindness (stale health, connection issues)
- Tier 4: Recovery scenarios (restart, state restoration)
"""
