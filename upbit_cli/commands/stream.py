"""
WebSocket stream commands: ticker, orderbook (public); my-order, my-asset (private).

Output is NDJSON (one JSON per line) to stdout. --count and --duration ensure agents do not hang.
Private streams require API credentials; JWT is passed to ws_client and masked in logs.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from typing import Any, List, Optional

import typer
from pydantic import BaseModel, ConfigDict, field_serializer

from upbit_cli.auth import get_credentials, generate_jwt, JWTOptions
from upbit_cli.ws_client import PING_INTERVAL, connect_and_stream

stream_app = typer.Typer(help="Real-time WebSocket streams (NDJSON to stdout).")


# ---------- Stream message models (compact) ----------


class TickerStreamCompact(BaseModel):
    """Minimal ticker from WS for token efficiency."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    type: Optional[str] = None
    code: Optional[str] = None
    trade_price: Optional[Decimal] = None
    change: Optional[str] = None
    acc_trade_volume_24h: Optional[Decimal] = None
    stream_type: Optional[str] = None

    @field_serializer("trade_price", "acc_trade_volume_24h", when_used="json")
    def _ser(self, v: Optional[Decimal]) -> str:
        if v is None:
            return "0"
        return format(v, "f")

    @classmethod
    def from_ws_message(cls, msg: Any) -> Optional["TickerStreamCompact"]:
        if not isinstance(msg, dict):
            return None
        try:
            return cls(
                type=msg.get("type"),
                code=msg.get("code"),
                trade_price=Decimal(str(msg["trade_price"])) if msg.get("trade_price") is not None else None,
                change=msg.get("change"),
                acc_trade_volume_24h=Decimal(str(msg["acc_trade_volume_24h"])) if msg.get("acc_trade_volume_24h") is not None else None,
                stream_type=msg.get("stream_type"),
            )
        except Exception:
            return None


class OrderbookStreamCompact(BaseModel):
    """Minimal orderbook unit from WS."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    type: Optional[str] = None
    code: Optional[str] = None
    total_ask_size: Optional[Decimal] = None
    total_bid_size: Optional[Decimal] = None
    stream_type: Optional[str] = None

    @field_serializer("total_ask_size", "total_bid_size", when_used="json")
    def _ser(self, v: Optional[Decimal]) -> str:
        if v is None:
            return "0"
        return format(v, "f")

    @classmethod
    def from_ws_message(cls, msg: Any) -> Optional["OrderbookStreamCompact"]:
        if not isinstance(msg, dict):
            return None
        try:
            return cls(
                type=msg.get("type"),
                code=msg.get("code"),
                total_ask_size=Decimal(str(msg["total_ask_size"])) if msg.get("total_ask_size") is not None else None,
                total_bid_size=Decimal(str(msg["total_bid_size"])) if msg.get("total_bid_size") is not None else None,
                stream_type=msg.get("stream_type"),
            )
        except Exception:
            return None


class MyOrderStreamCompact(BaseModel):
    """Flattened myOrder message for agent token efficiency (1-depth JSONL)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    type: Optional[str] = None
    uuid: Optional[str] = None
    market: Optional[str] = None
    side: Optional[str] = None
    ord_type: Optional[str] = None
    state: Optional[str] = None
    price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    executed_volume: Optional[Decimal] = None
    created_at: Optional[str] = None
    stream_type: Optional[str] = None

    @field_serializer("price", "volume", "executed_volume", when_used="json")
    def _ser(self, v: Optional[Decimal]) -> str:
        if v is None:
            return "0"
        return format(v, "f")

    @classmethod
    def from_ws_message(cls, msg: Any) -> Optional["MyOrderStreamCompact"]:
        if not isinstance(msg, dict):
            return None
        try:
            def _dec(key: str) -> Optional[Decimal]:
                val = msg.get(key)
                if val is None:
                    return None
                return Decimal(str(val))

            return cls(
                type=msg.get("type"),
                uuid=msg.get("uuid"),
                market=msg.get("market"),
                side=msg.get("side"),
                ord_type=msg.get("ord_type"),
                state=msg.get("state"),
                price=_dec("price"),
                volume=_dec("volume"),
                executed_volume=_dec("executed_volume"),
                created_at=msg.get("created_at"),
                stream_type=msg.get("stream_type"),
            )
        except Exception:
            return None


class MyAssetStreamCompact(BaseModel):
    """Flattened myAsset message for agent token efficiency (1-depth JSONL)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    type: Optional[str] = None
    currency: Optional[str] = None
    balance: Optional[Decimal] = None
    locked: Optional[Decimal] = None
    avg_buy_price: Optional[Decimal] = None
    stream_type: Optional[str] = None

    @field_serializer("balance", "locked", "avg_buy_price", when_used="json")
    def _ser(self, v: Optional[Decimal]) -> str:
        if v is None:
            return "0"
        return format(v, "f")

    @classmethod
    def from_ws_message(cls, msg: Any) -> Optional["MyAssetStreamCompact"]:
        if not isinstance(msg, dict):
            return None
        try:
            def _dec(key: str) -> Optional[Decimal]:
                val = msg.get(key)
                if val is None:
                    return None
                return Decimal(str(val))

            return cls(
                type=msg.get("type"),
                currency=msg.get("currency"),
                balance=_dec("balance"),
                locked=_dec("locked"),
                avg_buy_price=_dec("avg_buy_price"),
                stream_type=msg.get("stream_type"),
            )
        except Exception:
            return None


def _print_stderr_error(error_code: str, message: str, **kwargs: Any) -> None:
    payload = {"success": False, "error_code": error_code, "message": message, **kwargs}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    sys.stderr.flush()


def _run_stream(
    stream_type: str,
    markets: List[str],
    format_type: str,
    count: int,
    duration: int,
    compact: bool,
    on_message_cb: Optional[Any],
    token: Optional[str] = None,
) -> None:
    try:
        asyncio.run(
            connect_and_stream(
                stream_type=stream_type,
                codes=markets,
                format_type=format_type,
                token=token,
                count=count,
                duration_sec=float(duration) if duration else 0,
                ping_interval=PING_INTERVAL,
                ping_timeout=20,
                on_message=on_message_cb,
            )
        )
    except KeyboardInterrupt:
        _print_stderr_error("STREAM_INTERRUPTED", "Stream terminated by user (SIGINT).")
        raise typer.Exit(0)
    except Exception as e:
        _print_stderr_error("STREAM_ERROR", str(e))
        raise typer.Exit(1)


# ---------- Public: ticker ----------


@stream_app.command("ticker")
def ticker(
    market: str = typer.Option(..., "--market", "-m", help="Market code, e.g. KRW-BTC."),
    count: int = typer.Option(0, "--count", "-c", help="Stop after N messages (0 = unlimited)."),
    duration: int = typer.Option(0, "--duration", "-d", help="Stop after N seconds (0 = unlimited)."),
    format_type: str = typer.Option("default", "--format", "-f", help="default or simple (Upbit DEFAULT/SIMPLE)."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Output compact JSON (default: compact)."),
) -> None:
    """Stream ticker updates as NDJSON. Use --count or --duration to avoid infinite run."""
    markets = [m.strip() for m in market.split(",") if m.strip()]
    if not markets:
        _print_stderr_error("VALIDATION_ERROR", "At least one market required.")
        raise typer.Exit(1)
    fmt = "SIMPLE" if format_type.lower() == "simple" else "DEFAULT"

    def on_message(msg: Any) -> Optional[str]:
        if compact:
            t = TickerStreamCompact.from_ws_message(msg)
            if t is not None:
                return t.model_dump_json(exclude_none=True)
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))

    _run_stream("ticker", markets, fmt, count, duration, compact, on_message, token=None)


# ---------- Public: orderbook ----------


@stream_app.command("orderbook")
def orderbook(
    market: str = typer.Option(..., "--market", "-m", help="Market code, e.g. KRW-BTC."),
    count: int = typer.Option(0, "--count", "-c", help="Stop after N messages (0 = unlimited)."),
    duration: int = typer.Option(0, "--duration", "-d", help="Stop after N seconds (0 = unlimited)."),
    format_type: str = typer.Option("default", "--format", "-f", help="default or simple."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Output compact JSON (default: compact)."),
) -> None:
    """Stream orderbook updates as NDJSON. Use --count or --duration to avoid infinite run."""
    markets = [m.strip() for m in market.split(",") if m.strip()]
    if not markets:
        _print_stderr_error("VALIDATION_ERROR", "At least one market required.")
        raise typer.Exit(1)
    fmt = "SIMPLE" if format_type.lower() == "simple" else "DEFAULT"

    def on_message(msg: Any) -> Optional[str]:
        if compact:
            ob = OrderbookStreamCompact.from_ws_message(msg)
            if ob is not None:
                return ob.model_dump_json(exclude_none=True)
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))

    _run_stream("orderbook", markets, fmt, count, duration, compact, on_message, token=None)


# ---------- Private: my-order ----------


@stream_app.command("my-order")
def my_order(
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Optional market filter (comma-separated). Omit for all markets."),
    count: int = typer.Option(0, "--count", "-c", help="Stop after N messages (0 = unlimited)."),
    duration: int = typer.Option(0, "--duration", "-d", help="Stop after N seconds (0 = unlimited)."),
    format_type: str = typer.Option("default", "--format", "-f", help="default or simple."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Output compact JSON (default: compact)."),
) -> None:
    """Stream my order events (place/exec/cancel) as NDJSON. Requires API credentials. Use --count or --duration to avoid infinite run."""
    creds = get_credentials()
    if creds is None:
        _print_stderr_error(
            "AUTH_ERROR",
            "Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
            suggested_action="terminate_and_ask_human",
        )
        raise typer.Exit(3)
    token = generate_jwt(creds, JWTOptions())
    markets = [m.strip() for m in (market or "").split(",") if m.strip()]

    fmt = "SIMPLE" if format_type.lower() == "simple" else "DEFAULT"

    def on_message(msg: Any) -> Optional[str]:
        if compact:
            o = MyOrderStreamCompact.from_ws_message(msg)
            if o is not None:
                return o.model_dump_json(exclude_none=True)
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))

    _run_stream("myOrder", markets, fmt, count, duration, compact, on_message, token=token)


# ---------- Private: my-asset ----------


@stream_app.command("my-asset")
def my_asset(
    count: int = typer.Option(0, "--count", "-c", help="Stop after N messages (0 = unlimited)."),
    duration: int = typer.Option(0, "--duration", "-d", help="Stop after N seconds (0 = unlimited)."),
    format_type: str = typer.Option("default", "--format", "-f", help="default or simple."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Output compact JSON (default: compact)."),
) -> None:
    """Stream my asset balance updates as NDJSON. Requires API credentials. Use --count or --duration to avoid infinite run."""
    creds = get_credentials()
    if creds is None:
        _print_stderr_error(
            "AUTH_ERROR",
            "Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
            suggested_action="terminate_and_ask_human",
        )
        raise typer.Exit(3)
    token = generate_jwt(creds, JWTOptions())
    fmt = "SIMPLE" if format_type.lower() == "simple" else "DEFAULT"

    def on_message(msg: Any) -> Optional[str]:
        if compact:
            a = MyAssetStreamCompact.from_ws_message(msg)
            if a is not None:
                return a.model_dump_json(exclude_none=True)
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))

    _run_stream("myAsset", [], fmt, count, duration, compact, on_message, token=token)
