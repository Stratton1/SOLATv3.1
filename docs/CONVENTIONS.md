# SOLAT Coding Conventions

## Python Engine

### Code Style
- **Formatter**: ruff format
- **Linter**: ruff check
- **Type checker**: mypy (strict mode)
- **Line length**: 100 characters
- **Imports**: Sorted by ruff (isort rules)

### Naming
- **Modules**: `snake_case` (e.g., `broker_adapter.py`)
- **Classes**: `PascalCase` (e.g., `BrokerAdapter`)
- **Functions/Methods**: `snake_case` (e.g., `get_positions`)
- **Constants**: `SCREAMING_SNAKE_CASE` (e.g., `MAX_RETRIES`)
- **Private**: Single underscore prefix (e.g., `_internal_method`)

### Domain Models
- Use Pydantic `BaseModel` for all domain objects
- Use `Decimal` for all price/quantity values (never float)
- Make models immutable where possible (`frozen = True`)
- Use `UUID` for internal IDs, `str` for broker IDs

### Logging
```python
from solat_engine.logging import get_logger
logger = get_logger(__name__)

# Use structured logging
logger.info("Order submitted", extra={"order_id": str(order.id), "symbol": order.symbol})

# Never log sensitive data
# BAD: logger.info(f"API key: {api_key}")
# GOOD: logger.info("API key configured: %s", bool(api_key))
```

### Error Handling
- Define specific exceptions in `solat_engine/exceptions.py`
- Always catch specific exceptions, not bare `except:`
- Log errors with full context before re-raising
- Use `httpx.HTTPStatusError` for HTTP errors

### Testing
- Test files: `test_<module>.py`
- Use `pytest` with `pytest-asyncio` for async tests
- Aim for >80% coverage on core logic
- Use fixtures for common setup

## TypeScript/React UI

### Code Style
- **Formatter**: Prettier (via ESLint)
- **Linter**: ESLint with TypeScript rules
- **Line length**: 100 characters

### Naming
- **Files**: `PascalCase` for components, `camelCase` for utilities
- **Components**: `PascalCase` (e.g., `StatusScreen.tsx`)
- **Hooks**: `use` prefix (e.g., `useEngineHealth.ts`)
- **Types/Interfaces**: `PascalCase` (e.g., `HealthData`)

### Components
```typescript
// Props interface defined above component
interface StatusScreenProps {
  health: HealthData | null;
  isLoading: boolean;
}

// Export named function (not default)
export function StatusScreen({ health, isLoading }: StatusScreenProps) {
  // ...
}
```

### State Management
- Use React hooks (`useState`, `useEffect`, `useCallback`)
- Extract complex state to custom hooks
- Avoid prop drilling beyond 2 levels

## Run Artefacts

### Directory Structure
```
data/runs/{run_id}/
├── config.json       # Configuration snapshot
├── signals.parquet   # Generated signals
├── orders.parquet    # Orders placed
├── fills.parquet     # Order fills
├── equity.parquet    # Equity curve
├── metrics.json      # Performance metrics
└── logs/
    ├── engine.log    # Full engine log
    └── trades.log    # Trade-specific log
```

### Run ID Format
```
{type}_{date}_{time}_{uuid8}

Examples:
- backtest_20240115_143022_a1b2c3d4
- paper_20240115_160000_b2c3d4e5
- live_20240115_090000_c3d4e5f6
```

### Metrics JSON Structure
```json
{
  "run_id": "backtest_20240115_143022_a1b2c3d4",
  "strategy_id": "elite8_momentum",
  "symbol": "EURUSD",
  "timeframe": "1h",
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-15T00:00:00Z",
  "initial_capital": 10000.00,
  "final_capital": 10523.45,
  "total_return_pct": 5.23,
  "max_drawdown_pct": 2.15,
  "sharpe_ratio": 1.85,
  "total_trades": 42,
  "win_rate": 0.62,
  "profit_factor": 1.95
}
```

## Git Conventions

### Branches
- `main`: Production-ready code
- `develop`: Integration branch
- `feature/*`: New features
- `fix/*`: Bug fixes
- `release/*`: Release preparation

### Commits
- Use conventional commits format
- Present tense, imperative mood

```
feat(engine): add IG broker REST client
fix(ui): correct WebSocket reconnection logic
docs: update architecture diagram
test(engine): add backtest engine unit tests
```

### Pull Requests
- Link to related issues
- Include test coverage
- Update documentation if needed
- Require at least one review
