# UI Backend Requests - Track 1: Settings Overhaul

The following backend changes are requested to support the new Settings dashboard functionality.

## 1. Dynamic IG Credential Management
Currently, the engine loads credentials exclusively from `.env`. To allow runtime updates from the UI, we need endpoints to set and persist these credentials.

**Endpoint:** `POST /config/ig/credentials`
**Payload:**
```json
{
  "environment": "DEMO" | "LIVE",
  "api_key": "string",
  "username": "string",
  "password": "string",
  "account_id": "string" (optional)
}
```
**Expected Behavior:** Engine updates its internal settings and optionally persists them to a local configuration file (e.g., `data/config.json`) or updates the `.env`.

---

## 2. Environment-Specific Auth Testing
The current `/ig/test-login` uses the global `IG_ACC_TYPE`. We need to be able to test DEMO or LIVE credentials independently of the current engine mode.

**Endpoint:** `POST /ig/test-login`
**Query Parameter:** `env=demo|live` (optional, defaults to current mode)
**Payload:** (optional) allow passing temporary credentials to test before saving.

---

## 3. Data Storage Metadata
To improve the Data Explorer, additional metadata about Parquet partitions would be useful.

**Endpoint:** `GET /data/summary`
**Addition:** Include `disk_usage_bytes` and `last_updated_ts` per partition if possible.
