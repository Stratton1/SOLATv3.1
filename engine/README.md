# SOLAT Trading Engine

Python trading engine for SOLAT v3.1.

## Installation

```bash
# With uv (recommended)
uv pip install -e ".[dev]"

# With pip
pip install -e ".[dev]"
```

## Usage

```bash
# Run the server
uvicorn solat_engine.main:app --host 127.0.0.1 --port 8765 --reload

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy solat_engine
```

## Structure

```
solat_engine/
├── domain/         # Domain models (Bar, Order, Position, etc.)
├── interfaces/     # Abstract base classes
├── runtime/        # Event bus, artefacts
├── config.py       # Configuration
├── logging.py      # Logging setup
└── main.py         # FastAPI application
```
