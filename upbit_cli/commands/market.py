"""
Market data commands: ticker, orderbook, candles.

All numeric fields use Decimal and serialize as strings for precision and token efficiency.
Compact mode reduces payload size for AI agents; --limit caps array length.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from typing import Any, List, Optional

import typer
from pydantic import BaseModel, ConfigDict, field_serializer
from rich.console import Console
from rich.table import Table

from upbit_cli.http_client import UpbitAPIError, request_json

market_app = typer.Typer(help="Market data: tickers, orderbooks, candles.")

# ---------- Ticker models ----------


class TickerRaw(BaseModel):
    """Raw Upbit ticker response (subset of GET /ticker)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    market: str
    trade_price: Decimal
    opening_price: Decimal
    high_price: Decimal
    low_price: Decimal
    prev_closing_price: Decimal
    change: str
    change_price: Decimal
    change_rate: Decimal
    signed_change_price: Decimal
    signed_change_rate: Decimal
    acc_trade_price_24h: Decimal
    acc_trade_volume_24h: Decimal
    trade_timestamp: int

    @field_serializer(
        "trade_price",
        "opening_price",
        "high_price",
        "low_price",
        "prev_closing_price",
        "change_price",
        "change_rate",
        "signed_change_price",
        "signed_change_rate",
        "acc_trade_price_24h",
        "acc_trade_volume_24h",
        when_used="json",
    )
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class TickerCompact(BaseModel):
    """Token-efficient ticker for AI agents."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    market: str
    trade_price: Decimal
    change: str
    change_price: Decimal
    change_rate: Decimal
    acc_trade_price_24h: Decimal
    acc_trade_volume_24h: Decimal
    trade_timestamp: int

    @field_serializer(
        "trade_price",
        "change_price",
        "change_rate",
        "acc_trade_price_24h",
        "acc_trade_volume_24h",
        when_used="json",
    )
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_raw(cls, raw: TickerRaw) -> TickerCompact:
        return cls(
            market=raw.market,
            trade_price=raw.trade_price,
            change=raw.change,
            change_price=raw.change_price,
            change_rate=raw.change_rate,
            acc_trade_price_24h=raw.acc_trade_price_24h,
            acc_trade_volume_24h=raw.acc_trade_volume_24h,
            trade_timestamp=raw.trade_timestamp,
        )


# ---------- Orderbook models ----------


class OrderbookUnit(BaseModel):
    """Single level in orderbook_units."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    ask_price: Decimal
    bid_price: Decimal
    ask_size: Decimal
    bid_size: Decimal

    @field_serializer("ask_price", "bid_price", "ask_size", "bid_size", when_used="json")
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class OrderbookRaw(BaseModel):
    """Raw Upbit orderbook (GET /orderbook)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    market: str
    timestamp: int
    orderbook_units: List[OrderbookUnit]


class OrderbookCompact(BaseModel):
    """Flattened orderbook: top N bids and asks only."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    market: str
    timestamp: int
    bids: List[dict]  # [{"price": str, "size": str}, ...]
    asks: List[dict]


# ---------- Candle models ----------


class CandleRaw(BaseModel):
    """Raw Upbit candle (minutes or days)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    market: str
    candle_date_time_kst: Optional[str] = None
    candle_acc_trade_volume: Decimal
    candle_acc_trade_price: Decimal
    opening_price: Decimal
    high_price: Decimal
    low_price: Decimal
    trade_price: Decimal
    timestamp: int

    @field_serializer(
        "candle_acc_trade_volume",
        "candle_acc_trade_price",
        "opening_price",
        "high_price",
        "low_price",
        "trade_price",
        when_used="json",
    )
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class CandleCompact(BaseModel):
    """Minimal candle for AI agents."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    timestamp: int
    opening_price: Decimal
    high_price: Decimal
    low_price: Decimal
    trade_price: Decimal
    candle_acc_trade_volume: Decimal

    @field_serializer(
        "opening_price",
        "high_price",
        "low_price",
        "trade_price",
        "candle_acc_trade_volume",
        when_used="json",
    )
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_raw(cls, raw: CandleRaw) -> CandleCompact:
        return cls(
            timestamp=raw.timestamp,
            opening_price=raw.opening_price,
            high_price=raw.high_price,
            low_price=raw.low_price,
            trade_price=raw.trade_price,
            candle_acc_trade_volume=raw.candle_acc_trade_volume,
        )


# ---------- Output helpers (stdout / stderr) ----------


def _is_rich(ctx: typer.Context) -> bool:
    """True when global --output rich is set (for human debugging)."""
    root = ctx
    while getattr(root, "parent", None) is not None:
        root = root.parent
    if not getattr(root, "obj", None):
        return False
    out = getattr(root.obj, "output", None)
    return out is not None and getattr(out, "value", str(out)) == "rich"


def _print_success_stdout(data: Any) -> None:
    payload = {"success": True, "data": data}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_rich_ticker(data: List[Any]) -> None:
    """Print ticker data as a Rich table (for --output rich)."""
    if not data:
        Console().print("No data")
        return
    t = Table(title="Ticker")
    for key in data[0].keys():
        t.add_column(key)
    for row in data:
        t.add_row(*[str(row.get(k, "")) for k in data[0].keys()])
    Console().print(t)


def _print_rich_orderbook(data: Any) -> None:
    """Print orderbook as Rich table (bids/asks or orderbook_units)."""
    t = Table(title=f"Orderbook — {data.get('market', '')}")
    t.add_column("Side", style="cyan")
    t.add_column("Price", justify="right")
    t.add_column("Size", justify="right")
    if "bids" in data and "asks" in data:
        for b in data.get("bids", [])[:10]:
            t.add_row("BID", str(b.get("price", "")), str(b.get("size", "")))
        for a in data.get("asks", [])[:10]:
            t.add_row("ASK", str(a.get("price", "")), str(a.get("size", "")))
    else:
        for u in data.get("orderbook_units", [])[:10]:
            t.add_row("BID", str(u.get("bid_price", "")), str(u.get("bid_size", "")))
            t.add_row("ASK", str(u.get("ask_price", "")), str(u.get("ask_size", "")))
    Console().print(t)


def _print_rich_candles(data: List[Any]) -> None:
    """Print candles as a Rich table (for --output rich)."""
    if not data:
        Console().print("No candles")
        return
    t = Table(title="Candles")
    for key in data[0].keys():
        t.add_column(key)
    for row in data:
        t.add_row(*[str(row.get(k, "")) for k in data[0].keys()])
    Console().print(t)


def _print_error_stderr(
    error_code: str,
    message: str,
    *,
    status_code: Optional[int] = None,
    details: Optional[dict] = None,
    exit_code: int = 1,
) -> None:
    out: dict = {"success": False, "error_code": error_code, "message": message}
    if status_code is not None:
        out["status_code"] = status_code
    if details:
        out["details"] = details
    err_str = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    print(err_str, file=sys.stderr)
    sys.stderr.flush()
    raise typer.Exit(code=exit_code)


# ---------- Ticker command ----------


async def _get_ticker_impl(market: str, compact: bool, use_rich: bool = False) -> None:
    raw_json = await request_json("GET", "/ticker", params={"markets": market})
    if not isinstance(raw_json, list) or not raw_json:
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Ticker response empty or not a list.",
            details={"raw": raw_json},
        )
    tickers_raw: List[TickerRaw] = [TickerRaw.model_validate(item) for item in raw_json]
    if compact:
        out = [TickerCompact.from_raw(t).model_dump(mode="json") for t in tickers_raw]
    else:
        out = [t.model_dump(mode="json") for t in tickers_raw]
    if use_rich:
        _print_rich_ticker(out)
    else:
        _print_success_stdout(out)


@market_app.command("get-ticker")
def get_ticker(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market symbol, e.g. KRW-BTC."),
    compact: bool = typer.Option(
        True,
        "--compact/--no-compact",
        help="Return compact JSON for AI agents (default: compact).",
    ),
) -> None:
    """Get latest ticker for a market. Output is pure JSON on stdout unless --output rich."""
    try:
        asyncio.run(_get_ticker_impl(market=market, compact=compact, use_rich=_is_rich(ctx)))
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details if exc.details else None,
            exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Orderbook command ----------


async def _get_orderbook_impl(market: str, limit: int, compact: bool, use_rich: bool = False) -> None:
    raw_json = await request_json("GET", "/orderbook", params={"markets": market})
    if not isinstance(raw_json, list) or not raw_json:
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Orderbook response empty or not a list.",
            details={"raw": raw_json},
        )
    ob = OrderbookRaw.model_validate(raw_json[0])
    if compact:
        units = ob.orderbook_units[:limit]
        bids = [{"price": format(u.bid_price, "f"), "size": format(u.bid_size, "f")} for u in units]
        asks = [{"price": format(u.ask_price, "f"), "size": format(u.ask_size, "f")} for u in units]
        out = {"market": ob.market, "timestamp": ob.timestamp, "bids": bids, "asks": asks}
    else:
        out = ob.model_dump(mode="json")
    if use_rich:
        _print_rich_orderbook(out)
    else:
        _print_success_stdout(out)


@market_app.command("get-orderbook")
def get_orderbook(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market symbol, e.g. KRW-BTC."),
    limit: int = typer.Option(
        5,
        "--limit",
        "-l",
        help="Max number of bid/ask levels when compact (default 5).",
    ),
    compact: bool = typer.Option(
        True,
        "--compact/--no-compact",
        help="Return top N levels only for AI agents (default: compact).",
    ),
) -> None:
    """Get orderbook for a market. With --compact, only top --limit levels."""
    try:
        asyncio.run(_get_orderbook_impl(market=market, limit=limit, compact=compact, use_rich=_is_rich(ctx)))
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details if exc.details else None,
            exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Candles command ----------


async def _get_candles_impl(
    market: str,
    unit: str,
    interval: Optional[int],
    limit: int,
    compact: bool,
    use_rich: bool = False,
) -> None:
    if unit == "minutes":
        path = f"/candles/minutes/{interval}"
        params: dict = {"market": market, "count": limit}
    else:
        path = "/candles/days"
        params = {"market": market, "count": limit}
    raw_json = await request_json("GET", path, params=params)
    if not isinstance(raw_json, list):
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Candles response was not a list.",
            details={"raw": raw_json},
        )
    candles_raw: List[CandleRaw] = [CandleRaw.model_validate(item) for item in raw_json]
    if compact:
        out = [CandleCompact.from_raw(c).model_dump(mode="json") for c in candles_raw]
    else:
        out = [c.model_dump(mode="json") for c in candles_raw]
    if use_rich:
        _print_rich_candles(out)
    else:
        _print_success_stdout(out)


@market_app.command("get-candles")
def get_candles(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market symbol, e.g. KRW-BTC."),
    unit: str = typer.Option(
        "minutes",
        "--unit",
        "-u",
        help="Candle type: 'minutes' or 'days'.",
    ),
    interval: Optional[int] = typer.Option(
        1,
        "--interval",
        "-i",
        help="Minute interval when unit is minutes (e.g. 1, 3, 5).",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-l",
        help="Number of candles (API count parameter, default 5).",
    ),
    compact: bool = typer.Option(
        True,
        "--compact/--no-compact",
        help="Return only essential OHLCV fields (default: compact).",
    ),
) -> None:
    """Get candles (minutes or days). --limit is passed to API as count."""
    if unit not in ("minutes", "days"):
        _print_error_stderr("VALIDATION_ERROR", "unit must be 'minutes' or 'days'", exit_code=1)
    try:
        asyncio.run(_get_candles_impl(market=market, unit=unit, interval=interval, limit=limit, compact=compact, use_rich=_is_rich(ctx)))
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details if exc.details else None,
            exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)
