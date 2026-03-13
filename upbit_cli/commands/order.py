"""
Order commands: chance, place, list, get, cancel, cancel-all.

Uses JWT. Place sends client-side identifier (UUID) for idempotency. --max-total enforces safety cap.
cancel-all fetches wait orders then deletes each (no single Upbit cancel-all endpoint).
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from typing import Any, List, Optional

import typer
from pydantic import BaseModel, ConfigDict, field_serializer
from rich.console import Console
from rich.table import Table

from upbit_cli.auth import get_credentials
from upbit_cli.http_client import AuthError, UpbitAPIError, request_json_private

order_app = typer.Typer(help="Orders (place, list, cancel). Requires API credentials.")


# ---------- Order models ----------


class OrderRaw(BaseModel):
    """Raw order from GET /v1/order(s)."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    uuid: str
    market: str
    side: str
    ord_type: str
    price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    state: str
    created_at: Optional[str] = None
    identifier: Optional[str] = None

    @field_serializer("price", "volume", when_used="json")
    def _ser_decimal(self, value: Optional[Decimal]) -> str:
        if value is None:
            return "0"
        return format(value, "f")


class OrderCompact(BaseModel):
    """Compact order for agents."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    uuid: str
    market: str
    side: str
    ord_type: str
    price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    state: str

    @field_serializer("price", "volume", when_used="json")
    def _ser_decimal(self, value: Optional[Decimal]) -> str:
        if value is None:
            return "0"
        return format(value, "f")

    @classmethod
    def from_raw(cls, raw: OrderRaw) -> OrderCompact:
        return cls(
            uuid=raw.uuid,
            market=raw.market,
            side=raw.side,
            ord_type=raw.ord_type,
            price=raw.price,
            volume=raw.volume,
            state=raw.state,
        )


# ---------- Output helpers ----------


def _is_rich(ctx: typer.Context) -> bool:
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


def _print_rich_orders(data: List[Any]) -> None:
    if not data:
        Console().print("No orders")
        return
    t = Table(title="Orders")
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
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    sys.stderr.flush()
    raise typer.Exit(code=exit_code)


# ---------- Chance ----------


async def _chance_impl(market: str, compact: bool, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    raw_json = await request_json_private(
        "GET", "/orders/chance", credentials=creds, params={"market": market}
    )
    if use_rich:
        if isinstance(raw_json, dict):
            _print_rich_orders([raw_json])
        else:
            _print_rich_orders([raw_json] if not isinstance(raw_json, list) else raw_json)
    else:
        _print_success_stdout(raw_json)


@order_app.command("chance")
def chance(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market symbol, e.g. KRW-BTC."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Compact output."),
) -> None:
    """Get order possibility for a market."""
    try:
        asyncio.run(_chance_impl(market=market, compact=compact, use_rich=_is_rich(ctx)))
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Place (with identifier and max-total) ----------


def _estimate_order_total(ord_type: str, price: Optional[float], volume: Optional[float]) -> float:
    if ord_type == "limit" and price is not None and volume is not None:
        return price * volume
    if ord_type == "price" and price is not None:
        return price
    return 0.0


async def _place_impl(
    market: str,
    side: str,
    ord_type: str,
    volume: Optional[float],
    price: Optional[float],
    max_total: float,
    compact: bool,
    use_rich: bool,
) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    body: dict = {
        "market": market,
        "side": side,
        "ord_type": ord_type,
        "identifier": uuid.uuid4().hex,
    }
    if volume is not None:
        body["volume"] = str(volume)
    if price is not None:
        body["price"] = str(price)

    total = _estimate_order_total(ord_type, price, volume)
    if max_total > 0 and total > max_total:
        _print_error_stderr(
            "SAFETY_LIMIT_EXCEEDED",
            f"Estimated order total ({total}) exceeds --max-total ({max_total}). Aborting.",
            details={"estimated_total": total, "max_total": max_total},
            exit_code=1,
        )

    raw_json = await request_json_private(
        "POST", "/orders", credentials=creds, json_body=body
    )
    if use_rich:
        _print_rich_orders([raw_json] if isinstance(raw_json, dict) else raw_json)
    else:
        _print_success_stdout(raw_json)


@order_app.command("place")
def place(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market symbol, e.g. KRW-BTC."),
    side: str = typer.Option(..., "--side", "-s", help="bid or ask."),
    ord_type: str = typer.Option("limit", "--ord-type", help="limit, price, or market."),
    volume: Optional[float] = typer.Option(None, "--volume", "-v", help="Order volume."),
    price: Optional[float] = typer.Option(None, "--price", "-p", help="Order price."),
    max_total: float = typer.Option(
        0,
        "--max-total",
        help="Safety cap: abort if estimated total exceeds this (0 = unlimited).",
    ),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Compact output."),
) -> None:
    """Place an order. A client-side UUID is sent as identifier for idempotency. Use --max-total to cap order value."""
    try:
        asyncio.run(
            _place_impl(
                market=market,
                side=side,
                ord_type=ord_type,
                volume=volume,
                price=price,
                max_total=max_total,
                compact=compact,
                use_rich=_is_rich(ctx),
            )
        )
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- List ----------


async def _list_impl(
    state: str,
    market: Optional[str],
    compact: bool,
    use_rich: bool,
) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    params: dict = {"state": state}
    if market:
        params["market"] = market
    raw_json = await request_json_private(
        "GET", "/orders", credentials=creds, params=params
    )
    if not isinstance(raw_json, list):
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Orders response was not a list.",
            details={"raw": raw_json},
        )
    orders_raw = [OrderRaw.model_validate(item) for item in raw_json]
    if compact:
        out = [OrderCompact.from_raw(o).model_dump(mode="json") for o in orders_raw]
    else:
        out = [o.model_dump(mode="json") for o in orders_raw]
    if use_rich:
        _print_rich_orders(out)
    else:
        _print_success_stdout(out)


@order_app.command("list")
def list_orders(
    ctx: typer.Context,
    state: str = typer.Option("wait", "--state", help="wait, done, or cancel."),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filter by market."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Compact output."),
) -> None:
    """List orders by state (wait/done/cancel)."""
    try:
        asyncio.run(
            _list_impl(
                state=state,
                market=market,
                compact=compact,
                use_rich=_is_rich(ctx),
            )
        )
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Get ----------


async def _get_impl(uuid_str: str, compact: bool, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    raw_json = await request_json_private(
        "GET", "/order", credentials=creds, params={"uuid": uuid_str}
    )
    if compact and isinstance(raw_json, dict):
        out = OrderCompact.from_raw(OrderRaw.model_validate(raw_json)).model_dump(mode="json")
    else:
        out = raw_json
    if use_rich:
        _print_rich_orders([out])
    else:
        _print_success_stdout(out)


@order_app.command("get")
def get_order(
    ctx: typer.Context,
    uuid_str: str = typer.Option(..., "--uuid", help="Order UUID."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Compact output."),
) -> None:
    """Get a single order by UUID."""
    try:
        asyncio.run(_get_impl(uuid_str=uuid_str, compact=compact, use_rich=_is_rich(ctx)))
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Cancel ----------


async def _cancel_impl(uuid_str: str, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    raw_json = await request_json_private(
        "DELETE", "/order", credentials=creds, json_body={"uuid": uuid_str}
    )
    if use_rich:
        _print_rich_orders([raw_json] if isinstance(raw_json, dict) else raw_json)
    else:
        _print_success_stdout(raw_json)


@order_app.command("cancel")
def cancel(
    ctx: typer.Context,
    uuid_str: str = typer.Option(..., "--uuid", help="Order UUID to cancel."),
) -> None:
    """Cancel a single order by UUID."""
    try:
        asyncio.run(_cancel_impl(uuid_str=uuid_str, use_rich=_is_rich(ctx)))
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)


# ---------- Cancel-all (smart: GET wait then DELETE each) ----------


async def _cancel_all_impl(market: str, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    raw_json = await request_json_private(
        "GET", "/orders", credentials=creds, params={"state": "wait", "market": market}
    )
    if not isinstance(raw_json, list):
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Orders response was not a list.",
            details={"raw": raw_json},
        )
    results: List[dict] = []
    for item in raw_json:
        uid = item.get("uuid") if isinstance(item, dict) else None
        if not uid:
            continue
        try:
            resp = await request_json_private(
                "DELETE", "/order", credentials=creds, json_body={"uuid": uid}
            )
            results.append(resp if isinstance(resp, dict) else {"uuid": uid, "result": resp})
        except Exception as e:
            results.append({"uuid": uid, "error": str(e)})
    if use_rich:
        _print_rich_orders(results)
    else:
        _print_success_stdout(results)


@order_app.command("cancel-all")
def cancel_all(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market to cancel all wait orders for."),
) -> None:
    """Cancel all wait orders for a market. Fetches wait orders then deletes each (no single Upbit endpoint)."""
    try:
        asyncio.run(_cancel_all_impl(market=market, use_rich=_is_rich(ctx)))
    except AuthError as exc:
        _print_error_stderr(exc.error_code, exc.message, exit_code=exc.exit_code)
    except UpbitAPIError as exc:
        _print_error_stderr(
            exc.error_code, exc.message,
            status_code=exc.status_code, details=exc.details, exit_code=exc.exit_code,
        )
    except Exception as exc:
        _print_error_stderr("UNEXPECTED_ERROR", str(exc), exit_code=1)
