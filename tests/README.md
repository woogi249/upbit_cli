# Test suite for upbit-cli

## Stack

- **pytest** – test runner
- **pytest-asyncio** – for async tests (e.g. HTTP client)
- **typer.testing.CliRunner** – invoke CLI without subprocess
- **respx** – mock `httpx`; **no real HTTP requests** to Upbit API
- **monkeypatch** / **tmp_path** – isolate auth config (no writes to real `~/.upbit`)

## Run locally

From the project root:

```bash
# Install dev dependencies (includes pytest, pytest-asyncio, respx)
poetry install

# Run all tests with verbose output
poetry run pytest -v

# Run a specific file or test
poetry run pytest tests/test_cli.py -v
poetry run pytest tests/test_auth.py tests/test_models.py -v
```

## What is tested

- **test_cli.py**: Stdout is valid JSON; stderr holds standardized error JSON on 429/network errors; no ANSI/Rich in stdout.
- **test_auth.py**: `mask_secret`, `load_from_config` (missing/invalid file → `None`), `save_config`, no raw secrets in `repr`.
- **test_models.py**: `TickerCompact.from_raw()` compaction and Decimal serialized as strings in JSON.
