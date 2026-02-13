# Implementation Plan - Test Suite Rehabilitation

## Phase 1: Infrastructure
- [x] Create `engine/tests/fixtures/app_fixtures.py` with standard mock providers
- [x] Update `engine/tests/conftest.py` to include new fixtures
- [x] Verify `psutil` is correctly mocked for infrastructure health tests

## Phase 2: Endpoint Migration
- [x] Migrate `test_ig_endpoints.py` to DI pattern
- [x] Migrate `test_execution_endpoints.py` to DI pattern
- [x] Migrate `test_market_routes.py` to DI pattern
- [x] Migrate `test_data_endpoints.py` to DI pattern
- [x] Migrate `test_catalog.py` to DI pattern

## Phase 3: Validation
- [x] Run full test suite: `pytest engine/tests -v --tb=short`
- [x] Achieve 100% pass rate (710/710 passed)
- [x] Verify no regressions in status page endpoints
