"""
Shared pytest fixtures and mocks for upbit-cli tests.

CRITICAL: No real HTTP requests to Upbit API. All HTTP is mocked via respx.
File system for auth tests uses tmp_path / monkeypatch to avoid touching real ~/.upbit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx
from typer.testing import CliRunner

UPBIT_BASE = "https://api.upbit.com/v1"


def _sample_ticker_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit ticker response for one market."""
    return [
        {
            "market": "KRW-BTC",
            "trade_date": "20240313",
            "trade_time": "12:00:00",
            "trade_date_kst": "20240313",
            "trade_time_kst": "21:00:00",
            "trade_timestamp": 1710000000000,
            "opening_price": 100000000.0,
            "high_price": 101000000.0,
            "low_price": 99000000.0,
            "trade_price": 100500000.0,
            "prev_closing_price": 100000000.0,
            "change": "RISE",
            "change_price": 500000.0,
            "change_rate": 0.005,
            "signed_change_price": 500000.0,
            "signed_change_rate": 0.005,
            "acc_trade_price_24h": 1234567890123.45,
            "acc_trade_volume_24h": 12345.67890123,
            "highest_52_week_price": 110000000.0,
            "lowest_52_week_price": 90000000.0,
        }
    ]


def _sample_orderbook_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit orderbook response for one market."""
    return [
        {
            "market": "KRW-BTC",
            "timestamp": 1710000000000,
            "orderbook_units": [
                {"ask_price": 100600000.0, "bid_price": 100500000.0, "ask_size": 0.5, "bid_size": 1.2},
                {"ask_price": 100700000.0, "bid_price": 100400000.0, "ask_size": 0.3, "bid_size": 0.8},
                {"ask_price": 100800000.0, "bid_price": 100300000.0, "ask_size": 1.0, "bid_size": 0.5},
            ],
        }
    ]


def _sample_candles_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit candles response (minutes or days)."""
    return [
        {
            "market": "KRW-BTC",
            "candle_date_time_kst": "2024-03-13T21:00:00",
            "candle_acc_trade_volume": 123.45,
            "candle_acc_trade_price": 12345678900.0,
            "opening_price": 100000000.0,
            "high_price": 100500000.0,
            "low_price": 99500000.0,
            "trade_price": 100200000.0,
            "timestamp": 1710000000000,
        },
    ]


def _sample_markets_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit market/all response."""
    return [
        {"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
        {"market": "KRW-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
        {"market": "USDT-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
    ]


def _sample_trades_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit trades/ticks response (sequential_id required for pagination)."""
    return [
        {
            "market": "KRW-BTC",
            "trade_date_utc": "2024-03-13",
            "trade_time_utc": "12:00:00",
            "timestamp": 1710000000000,
            "trade_price": 100500000.0,
            "trade_volume": 0.001,
            "sequential_id": 1000001,
            "ask_bid": "BID",
        },
    ]


def _sample_orderbook_instruments_payload() -> List[Dict[str, Any]]:
    """Minimal valid Upbit orderbook/instruments response."""
    return [
        {"market": "KRW-BTC", "quote_currency": "KRW", "tick_size": 1000.0, "supported_levels": [0]},
    ]


@pytest.fixture
def sample_ticker_response() -> List[Dict[str, Any]]:
    """Raw ticker JSON as returned by Upbit API (one market)."""
    return _sample_ticker_payload()


@pytest.fixture
def sample_orderbook_response() -> List[Dict[str, Any]]:
    """Raw orderbook JSON as returned by Upbit API (one market)."""
    return _sample_orderbook_payload()


@pytest.fixture
def sample_candles_response() -> List[Dict[str, Any]]:
    """Raw candles JSON as returned by Upbit API."""
    return _sample_candles_payload()


@pytest.fixture
def sample_markets_response() -> List[Dict[str, Any]]:
    """Raw market list JSON as returned by Upbit API (GET /market/all)."""
    return _sample_markets_payload()


@pytest.fixture
def sample_trades_response() -> List[Dict[str, Any]]:
    """Raw trades JSON as returned by Upbit API (GET /trades/ticks), includes sequential_id."""
    return _sample_trades_payload()


@pytest.fixture
def sample_orderbook_instruments_response() -> List[Dict[str, Any]]:
    """Raw orderbook instruments JSON as returned by Upbit API."""
    return _sample_orderbook_instruments_payload()


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CliRunner for invoking the app without subprocess. mix_stderr=False keeps stdout/stderr separate."""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_upbit_ticker_ok(sample_ticker_response: List[Dict[str, Any]]) -> respx.MockRouter:
    """Mock GET /v1/ticker to return 200 and sample ticker JSON."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{UPBIT_BASE}/ticker").mock(
            return_value=httpx.Response(200, json=sample_ticker_response)
        )
        yield router


@pytest.fixture
def mock_upbit_429() -> respx.MockRouter:
    """Mock GET /v1/ticker to return HTTP 429 Too Many Requests."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{UPBIT_BASE}/ticker").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"message": "Too Many Requests"}},
                headers={"Remaining-Req": "group=market; min=0; sec=0"},
            )
        )
        yield router


@pytest.fixture
def mock_upbit_500() -> respx.MockRouter:
    """Mock GET /v1/ticker to return HTTP 500 (retryable)."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{UPBIT_BASE}/ticker").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )
        yield router


@pytest.fixture
def fake_config_dir(tmp_path: Path) -> Path:
    """Temporary directory for config file (replaces ~/.upbit in tests)."""
    d = tmp_path / "upbit"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def fake_config_path(fake_config_dir: Path) -> Path:
    """Path to a config file that may or may not exist."""
    return fake_config_dir / "config.json"


def write_config(path: Path, access_key: str, secret_key: str) -> None:
    """Write a minimal config JSON to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"access_key": access_key, "secret_key": secret_key}, indent=2),
        encoding="utf-8",
    )
