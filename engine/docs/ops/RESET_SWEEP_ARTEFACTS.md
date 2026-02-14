# Resetting Sweep Artefacts

## Overview

Before running a new Grand Sweep, clear old results so the UI and scripts show only fresh data. The reset utility archives (default) or deletes old artefacts while preserving raw market data.

## What Gets Reset vs Preserved

### Always Reset (default targets)
| Target | Location |
|--------|----------|
| Sweep results | `data/sweep_results/*` |
| Backtest runs | `data/backtests/*` |
| Walk-forward artefacts | `data/artefacts/*` |
| Proposals | `data/proposals/*` |
| Allowlist | `data/allowlist.json` |
| Optimized variants | `data/optimized_variants.json` |
| Log files | `data/*.log` |

### Optional Targets (with flags)
| Target | Flag | Location |
|--------|------|----------|
| Tuning results | `--include-tuning` | `data/tuning/*` |
| Portfolio builds | `--include-portfolio` | `data/portfolio/*` |
| Hall-of-fame docs | `--include-docs` | `docs/GRAND_SWEEP_*.md` |

### Never Touched (protected)
| Target | Location | Reason |
|--------|----------|--------|
| OHLCV bars | `data/parquet/bars/` | Historical market data |
| Manifests | `data/parquet/manifests/` | Deduplication metadata |
| App logs | `data/logs/` | Application debugging |
| Credentials | `.env` | Secrets |
| Deployment config | `data/autopilot_v3.1_deployment.json` | Active config |

## Usage

### Dry Run (see what would happen)

```bash
# From repo root
pnpm reset:sweeps:dry

# Or directly
cd engine && python3 scripts/reset_sweep_artefacts.py --dry-run
```

### Archive Sweep Artefacts (safe default)

```bash
# From repo root
pnpm reset:sweeps

# Or directly
cd engine && python3 scripts/reset_sweep_artefacts.py --mode archive --yes
```

Archives to `data/_archive/YYYYMMDD_HHMMSS/` with an `ARCHIVE_MANIFEST.json`.

### Full Reset (sweeps + tuning + portfolio + docs)

```bash
# From repo root
pnpm reset:sweeps:full

# Or directly
cd engine && python3 scripts/reset_sweep_artefacts.py \
    --mode archive --yes \
    --include-tuning --include-portfolio --include-docs
```

### Delete Mode (permanent, use carefully)

```bash
cd engine && python3 scripts/reset_sweep_artefacts.py --mode delete --yes
```

Requires both `--mode delete` and `--yes`. Still writes a deletion record to `data/_archive/`.

## After Reset

1. **Verify UI**: The Library screen should show empty sweeps/backtests lists
2. **Run new sweep**: `python3 engine/scripts/run_grand_sweep.py --workers 6 --asset-classes fx`
3. **Check artefact index**: `curl http://127.0.0.1:8765/data/artefacts/index` should show only bars data

## Restoring from Archive

Archives are stored at `data/_archive/YYYYMMDD_HHMMSS/` with original directory structure preserved.

```bash
# List archives
ls engine/data/_archive/

# Check what was archived
cat engine/data/_archive/20260214_220000/ARCHIVE_MANIFEST.json

# Restore specific items (manual)
cp -r engine/data/_archive/20260214_220000/engine/data/sweep_results/* engine/data/sweep_results/
```

## Troubleshooting

### UI Still Shows Old Results
The artefact index endpoint scans `data/sweep_results/` and `data/backtests/` on each request. After reset, refresh the Library screen. If results persist, the engine may be caching — restart it.

### Archive Directory Growing
Old archives accumulate in `data/_archive/`. Periodically clean up:
```bash
# List archives with sizes
du -sh engine/data/_archive/*/

# Remove old archives (manual)
rm -rf engine/data/_archive/20260101_*/
```

### Script Reports Nothing to Reset
All target directories are already empty or missing. This is a no-op — safe to proceed with the new sweep.
