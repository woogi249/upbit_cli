"""
Pydantic model tests: compaction logic and Decimal serialization.

Ensures TickerCompact.from_raw drops unnecessary fields and Decimal values
are strictly serialized as strings in model_dump_json().
"""

from __future__ import annotations

import json
from decimal import Decimal

from upbit_cli.commands.market import TickerCompact, TickerRaw, TradeCompact, TradeRaw



def _raw_ticker_dict() -> dict:
    """Minimal dict that validates as TickerRaw (Upbit ticker subset)."""
    return {
        "market": "KRW-BTC",
        "trade_price": 100500000.0,
        "opening_price": 100000000.0,
        "high_price": 101000000.0,
        "low_price": 99000000.0,
        "prev_closing_price": 100000000.0,
        "change": "RISE",
        "change_price": 500000.0,
        "change_rate": 0.005,
        "signed_change_price": 500000.0,
        "signed_change_rate": 0.005,
        "acc_trade_price_24h": 1234567890123.45,
        "acc_trade_volume_24h": 12345.67890123,
        "trade_timestamp": 1710000000000,
    }


class TestTickerCompactFromRaw:
    """TickerCompact.from_raw must keep only essential fields and drop the rest."""

    def test_from_raw_drops_extra_fields(self) -> None:
        raw_dict = _raw_ticker_dict()
        raw = TickerRaw.model_validate(raw_dict)
        compact = TickerCompact.from_raw(raw)
        compact_dict = compact.model_dump()
        assert "opening_price" not in compact_dict
        assert "high_price" not in compact_dict
        assert "low_price" not in compact_dict
        assert compact.market == "KRW-BTC"
        assert compact.trade_price in (Decimal("100500000"), Decimal("100500000.0"))
        assert compact.change_rate == Decimal("0.005")
        assert compact.acc_trade_volume_24h == Decimal("12345.67890123")

    def test_compact_has_required_fields_only(self) -> None:
        raw = TickerRaw.model_validate(_raw_ticker_dict())
        compact = TickerCompact.from_raw(raw)
        allowed = {
            "market",
            "trade_price",
            "change",
            "change_price",
            "change_rate",
            "acc_trade_price_24h",
            "acc_trade_volume_24h",
            "trade_timestamp",
        }
        for key in compact.model_dump():
            assert key in allowed, f"Compact must not expose extra field: {key}"


class TestDecimalSerialization:
    """Decimal fields must serialize as strings in JSON to avoid float precision loss."""

    def test_compact_json_uses_strings_for_numeric_fields(self) -> None:
        raw = TickerRaw.model_validate(_raw_ticker_dict())
        compact = TickerCompact.from_raw(raw)
        dumped = compact.model_dump(mode="json")
        assert isinstance(dumped["trade_price"], str)
        assert isinstance(dumped["change_rate"], str)
        assert isinstance(dumped["acc_trade_volume_24h"], str)

    def test_model_dump_json_strictly_serializes_decimals_as_strings(self) -> None:
        raw = TickerRaw.model_validate(_raw_ticker_dict())
        compact = TickerCompact.from_raw(raw)
        json_str = compact.model_dump_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed["trade_price"], str)
        assert isinstance(parsed["change_price"], str)
        assert isinstance(parsed["change_rate"], str)
        assert isinstance(parsed["acc_trade_price_24h"], str)
        assert isinstance(parsed["acc_trade_volume_24h"], str)
        assert "100500000" in parsed["trade_price"] or parsed["trade_price"] == "100500000.0"


def _raw_trade_dict() -> dict:
    """Minimal dict that validates as TradeRaw (Upbit trades/ticks subset)."""
    return {
        "market": "KRW-BTC",
        "trade_date_utc": "2024-03-13",
        "trade_time_utc": "12:00:00",
        "timestamp": 1710000000000,
        "trade_price": 100500000.0,
        "trade_volume": 0.001,
        "sequential_id": 1000001,
        "ask_bid": "BID",
    }


class TestTradeCompactSequentialId:
    """TradeCompact must include sequential_id for pagination (--cursor)."""

    def test_compact_includes_sequential_id(self) -> None:
        raw = TradeRaw.model_validate(_raw_trade_dict())
        compact = TradeCompact.from_raw(raw)
        assert hasattr(compact, "sequential_id")
        assert compact.sequential_id == 1000001

    def test_compact_json_serializes_sequential_id(self) -> None:
        raw = TradeRaw.model_validate(_raw_trade_dict())
        compact = TradeCompact.from_raw(raw)
        dumped = compact.model_dump(mode="json")
        assert "sequential_id" in dumped
        assert dumped["sequential_id"] == 1000001
        assert isinstance(dumped["trade_price"], str)
        assert isinstance(dumped["trade_volume"], str)
