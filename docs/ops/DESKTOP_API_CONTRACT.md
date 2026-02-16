# Desktop API Contract

Version: `2026-02-15`

This document is the desktop-facing API contract for `apps/desktop`.  
It defines the minimum route/field guarantees the UI depends on.

## Scope

- Contract owner: Engine (`engine/solat_engine`)
- Consumer: Desktop (`apps/desktop/src/lib/engineClient.ts`)
- Transport: HTTP JSON + WebSocket
- Compatibility rule: additive changes are safe; removals/renames of fields below are breaking.

## REST Contract

### `GET /health`

- **Used by**: engine connectivity, global status strip
- **Required response fields**:
  - `status` (string; `"healthy"` means online)
  - `version` (string)
  - `time` (ISO string)
  - `uptime_seconds` (number)

### `GET /config`

- **Used by**: mode/config badges
- **Required response fields**:
  - `mode` (string)
  - `execution_mode` (string, optional fallback to `mode`)
  - `ig_configured` (boolean)
  - `data_dir` (string)

### `GET /universe`

- **Used by**: symbol selectors/catalogue
- **Required response shape**:
  - `instruments` (array)
  - `count` (number)
- **Required per instrument fields**:
  - `symbol` (string)
  - `display_name` (string)
  - `asset_class` (string)
  - `epic` (string | null, optional in UI but expected for IG-tradable)

### `GET /quotes?symbols=EURUSD,GBPUSD`

- **Used by**: watchlist, chart quote badges, polling fallback
- **Required query**:
  - `symbols` (comma-separated, optional)
- **Required response shape**:
  - `quotes` (object keyed by epic)
  - `count` (number)
- **Required per quote fields**:
  - `symbol` (string, optional but preferred)
  - `bid` (number)
  - `ask` (number)
  - `last` (number, optional; desktop derives mid if missing)
  - `time` (string timestamp, optional; desktop falls back to now)

### `GET /bars?symbol=EURUSD&tf=1h&limit=300`

- **Used by**: chart candles/history expansion
- **Required query**:
  - `symbol` or `epic` (one required)
  - `tf` (timeframe)
  - `limit` (optional)
- **Required response fields**:
  - `symbol` (string)
  - `tf` (string)
  - `bars` (array of `{ ts, o, h, l, c, v? }`)
  - `count` (number)

### `GET /account`

- **Used by**: broker connectivity card, connected state, balance readouts
- **Required response fields**:
  - `account_id` (string)
  - `balance` (number)
  - `equity` (number)
  - `available` (number)
  - `margin` (number)
  - `currency` (string | null)

### `GET /positions`

- **Used by**: dashboard positions, blotter hooks
- **Required response fields**:
  - `positions` (array)
  - `count` (number)

### `POST /orders/market`

- **Used by**: order ticket, quick trade, demo checklist
- **Required request body**:
  - `symbol` (string) or `epic` (string)
  - `direction` (`"BUY" | "SELL"`)
  - `size` (number > 0)
  - `stop_loss` (number, optional)
  - `take_profit` (number, optional)
- **Required response fields**:
  - `ok` (boolean)
  - `status` (string)
  - `intent_id` (string, optional)
  - `deal_id` (string, optional)
  - `error` (string, optional)

## Mapping Notes

- Engine quote payload maps to desktop quote model:
  - engine: `{ symbol?, bid, ask, last?, time? }`
  - desktop: `{ symbol, bid, ask, mid, ts }`
  - mapping:
    - `mid = last ?? (bid + ask) / 2`
    - `ts = time ?? new Date().toISOString()`

## Error Expectations

- `4xx`: user/action/config errors (invalid input, safety gate denied, missing credentials)
- `5xx`: engine-side failure (unexpected runtime error)
- Timeouts/transient failures:
  - desktop must retain last good state (stale-while-revalidate)
  - connectivity badge should not instantly flip offline on a single transient failure
