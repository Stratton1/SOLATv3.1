---
name: solat-engine-test
description: Suggests test file location, fixtures, and example test for engine code. Use when adding a test for X, how do I test IG client, or after adding an engine feature.
---

# SOLAT Engine Test Agent (6.1)

When the user asks **"Add test for X"**, **"How do I test IG client?"**, or after adding an engine feature, output **test file path**, **fixture sketch**, and **example test** following project conventions.

## Conventions

- **Location:** [engine/tests/](engine/tests/); file name `test_<module>.py` (e.g. test_ig_client.py for broker/ig/client.py).
- **Runner:** pytest with pytest-asyncio for async tests (`asyncio_mode = "auto"` in pyproject.toml).
- **Fixtures:** Use [engine/tests/conftest.py](engine/tests/conftest.py) for shared fixtures (e.g. temp_data_dir, reset_singletons). Add session- or function-scoped fixtures as needed (e.g. parquet_store, sample bars, mock IG client).
- **API mocking:** Use respx or httpx mock for HTTP; mock AsyncIGClient or responses for broker tests.
- **Coverage:** Aim for >80% on core logic; focus on business logic and error paths.

## Fixture patterns

- **temp_data_dir:** Already in conftest; use for ParquetStore or file-based tests.
- **Sample bars:** Build list of HistoricalBar or BarData for strategy/backtest tests.
- **Mock IG:** respx for httpx requests to demo-api.ig.com; or patch AsyncIGClient methods.
- **Async:** Use `@pytest.mark.asyncio` or rely on asyncio_mode; async fixtures with `@pytest.fixture` and `async def` where needed.

## Output format

1. **Test file path:** engine/tests/test_<module>.py.
2. **Fixtures:** List fixtures to add (in test file or conftest) and what they provide.
3. **Example test:** One or two example test functions (e.g. test_health_returns_200, test_ig_login_success) showing request/response and assert pattern.

Reference: [docs/CONVENTIONS.md](docs/CONVENTIONS.md) (Testing), [engine/tests/conftest.py](engine/tests/conftest.py).
