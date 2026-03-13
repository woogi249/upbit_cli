# upbit-cli

**EN** — An AI-agent-first CLI for [Upbit](https://upbit.com) (South Korean crypto exchange). Built with Typer, httpx, and Pydantic. Output is **predictable JSON** on stdout and **standardized errors** on stderr so LLM agents (AutoGPT, MCP, etc.) can call it from the terminal and parse results reliably.

**KR** — 업비트(Upbit) 전용 CLI로, **AI 에이전트**가 터미널에서 호출하고 JSON으로 결과를 파싱하기 쉽게 설계되었습니다. 사람도 사용할 수 있지만, 제1의 타겟은 LLM·봇입니다.

---

## Why this CLI is perfect for AI Agents

1. **Pure JSON on stdout**  
   Every successful command prints a single JSON object to stdout: `{"success": true, "data": ...}`. No logos, progress bars, or log lines that would break `json.loads()`.

2. **Standardized errors on stderr**  
   Failures are emitted only to stderr as JSON: `{"success": false, "error_code": "...", "message": "...", "status_code": ..., "details": {...}}`. Exit codes are semantic (e.g. 1 = general, 2 = network, 3 = auth). No raw stack traces on stdout.

3. **Compact mode and limits**  
   `--compact` (default for ticker/orderbook/candles) returns a minimal, flattened payload (price, change, volume, etc.) to save token context. Orderbook and candles support `--limit` so agents don’t blow their context window.

4. **Stable numerics**  
   Prices and volumes use `Decimal` and are serialized as **strings** in JSON to avoid float precision issues.

5. **Auth without leaking secrets**  
   Credentials via `UPBIT_ACCESS_KEY` and `UPBIT_SECRET_KEY` (env) or `~/.upbit/config.json`. Secrets are never printed; masking (e.g. `abcd****wxyz`) is used in any debug representation.

6. **Self-documenting**  
   `upbit --help` and `upbit market get-ticker --help` (and similar) give clear, English help so agents can discover usage.

---

## Installation

```bash
poetry install
# or
pip install .
```

Then run:

```bash
upbit --help
```

---

## Usage

### Get ticker (compact, AI-friendly)

```bash
upbit market get-ticker --market KRW-BTC --compact
```

**Example stdout:**

```json
{"success":true,"data":[{"market":"KRW-BTC","trade_price":"100500000.0","change":"RISE","change_price":"500000.0","change_rate":"0.005","acc_trade_price_24h":"1234567890123.45","acc_trade_volume_24h":"12345.67890123","trade_timestamp":1710000000000}]}
```

### Get ticker (full raw schema)

```bash
upbit market get-ticker --market KRW-BTC --no-compact
```

Returns the full Upbit ticker shape (validated by Pydantic, Decimals as strings).

### Orderbook and candles

```bash
upbit market get-orderbook --market KRW-BTC --limit 5 --compact
upbit market get-candles --market KRW-BTC --unit minutes --interval 1 --limit 5 --compact
```

### Authentication (for future private endpoints)

Set env vars (recommended for agents):

```bash
export UPBIT_ACCESS_KEY="your-access-key"
export UPBIT_SECRET_KEY="your-secret-key"
```

Or run `upbit configure` to interactively save credentials to `~/.upbit/config.json` (prompts for access key and secret key; secret is masked; file is chmod 0o600).

---

## Development

```bash
poetry install
poetry run pytest tests/ -v
```

---

## License

MIT.
