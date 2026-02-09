---
name: solat-api-contract-test
description: Suggests test cases for REST and WebSocket contracts (status codes, response shape, error cases). Use when adding a test for a new endpoint or editing api/.
---

# SOLAT API Contract Test Agent (6.2)

When the user asks **"Add test for new endpoint"** or when editing [engine/solat_engine/api/](engine/solat_engine/api/), output **test cases** (status + body/WS) so contract regressions are caught.

## Existing patterns

- **test_health.py:** GET /health → 200, body has status, version, time, uptime_seconds.
- **test_ig_endpoints.py:** IG routes with mocked httpx/respx; 200/401/422 as appropriate.
- **test_backtest_endpoints.py:** POST /backtest with request body → 200 or 202; job status; result shape.
- **test_execution_endpoints.py:** Execution routes; auth or config-dependent behaviour.
- **test_data_endpoints.py:** Data sync, bars, quality endpoints.

## Test case template

For each route:

1. **Success (200/201/202):** Method + path + (optional) body/query → expect status + response shape (keys, types). Use TestClient (FastAPI) or httpx; assert response.status_code and response.json() keys/values.
2. **Validation error (422):** Invalid or missing body/query → expect 422; optional assert on error detail shape.
3. **Auth/business (401/403/404):** Where applicable (e.g. IG not configured, invalid run_id) → expect appropriate status.
4. **WebSocket:** If the route or feature involves WS, test message type and payload shape (e.g. connect, send subscribe, assert message type and channel).

## Output format

1. **Route and method** (e.g. POST /backtest/run).
2. **Test cases:** List of (description, request, expected status, expected body/WS keys or snippet).
3. **Fixture:** Any client or mock needed (e.g. TestClient(app), respx mock for IG).

Reference: [engine/tests/test_health.py](engine/tests/test_health.py), [engine/tests/test_backtest_endpoints.py](engine/tests/test_backtest_endpoints.py), [engine/tests/test_ig_endpoints.py](engine/tests/test_ig_endpoints.py).
