# IG Integration (SOLAT v3.1)

This document describes the IG-only integration used by SOLAT for account data, market data, and order execution.

## Credentials and environment

- Required:
  - `IG_API_KEY`
  - `IG_USERNAME`
  - `IG_PASSWORD`
- Mode/profile is controlled by existing SOLAT settings and execution gates.
- Secrets remain server-side in the engine; UI never receives CST/X-SECURITY-TOKEN.

## REST and streaming flow

1. Engine authenticates with IG via REST session login.
2. Engine uses CST + X-SECURITY-TOKEN for REST calls.
3. For Lightstreamer, engine uses:
   - endpoint returned by session login (never hardcoded)
   - account id as user
   - password format: `CST-{token}|XST-{token}`
4. Engine normalizes data into SOLAT contracts consumed by desktop.

## Canonical route surface

- `GET /account`
- `GET /positions`
- `GET /orders`
- `GET /universe`
- `GET /quotes?epics=...` (also accepts `symbols` for desktop compatibility)
- `GET /bars?epic=...&tf=...&limit=...` (also accepts `symbol`)
- `POST /orders/market` (DEMO-first in current phase)
- `POST /orders/working`
- `PUT /positions/{dealId}`
- `DELETE /positions/{dealId}`

## WS event contract

- `quote_update`
- `bar_update`
- `order_event`
- `position_event`
- `market_status`
- `execution_event`
- `heartbeat`

Desktop keeps one app-level WebSocket and fans out events to feature hooks.

## Rate limits and retry policy

- REST uses IG rate limiter wrapper and bounded retry/backoff.
- 401 handling triggers re-auth and token refresh path.
- 429 and transient failures use exponential backoff.
- Streaming reconnection uses jittered backoff and stale-feed detection.

## Symbol universe

- Universe is catalogue-backed and IG-epic keyed.
- Only instruments with mapped epics are included.
- `/universe` is the authoritative list for UI symbol pickers and subscriptions.

## DEMO-first execution safety

- Market order endpoint is DEMO-only in this phase.
- Existing execution gate workflow for LIVE remains in place.
- Routing still passes through execution controls (arm state, risk checks, kill switch).

## Notes

- Historical bars are currently served from local store through canonical `/bars` contract.
- Streaming and REST paths remain IG-only; no external market data vendor is introduced.

## References

- https://labs.ig.com/getting-started.html
- https://labs.ig.com/rest-trading-api-guide.html
- https://labs.ig.com/streaming-api-guide.html
- https://labs.ig.com/faq.html
