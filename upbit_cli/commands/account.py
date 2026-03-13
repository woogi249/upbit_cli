"""
Account (asset) commands: balance.

Requires JWT; uses request_json_private. BalanceCompact includes total_amount (balance + locked).
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

from upbit_cli.auth import get_credentials
from upbit_cli.http_client import AuthError, UpbitAPIError, request_json_private

account_app = typer.Typer(help="Account balances (requires API credentials).")


# ---------- Balance models ----------


class BalanceRaw(BaseModel):
    """Raw balance from GET /v1/accounts."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    avg_buy_price_modified: bool = False
    unit_currency: str = "KRW"

    @field_serializer("balance", "locked", "avg_buy_price", when_used="json")
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class BalanceCompact(BaseModel):
    """Compact balance with total_amount (balance + locked) for agents."""

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)

    currency: str
    balance: Decimal
    locked: Decimal
    total_amount: Decimal
    avg_buy_price: Decimal

    @field_serializer("balance", "locked", "total_amount", "avg_buy_price", when_used="json")
    def _ser_decimal(self, value: Decimal) -> str:
        return format(value, "f")

    @classmethod
    def from_raw(cls, raw: BalanceRaw) -> BalanceCompact:
        total = raw.balance + raw.locked
        return cls(
            currency=raw.currency,
            balance=raw.balance,
            locked=raw.locked,
            total_amount=total,
            avg_buy_price=raw.avg_buy_price,
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


def _print_rich_balance(data: List[Any]) -> None:
    if not data:
        Console().print("No balances")
        return
    t = Table(title="Balances")
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


# ---------- Balance command ----------


async def _balance_impl(
    hide_dust: bool,
    compact: bool,
    use_rich: bool = False,
) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(
            message="Missing API credentials. Set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY or run 'upbit configure'.",
        )
    raw_json = await request_json_private("GET", "/accounts", credentials=creds)
    if not isinstance(raw_json, list):
        raise UpbitAPIError(
            error_code="INVALID_RESPONSE",
            message="Accounts response was not a list.",
            details={"raw": raw_json},
        )
    balances_raw: List[BalanceRaw] = [BalanceRaw.model_validate(item) for item in raw_json]
    if compact:
        compacts = [BalanceCompact.from_raw(b) for b in balances_raw]
        if hide_dust:
            compacts = [c for c in compacts if c.total_amount > 0]
        out = [c.model_dump(mode="json") for c in compacts]
    else:
        # Raw: still filter dust if hide_dust and add total_amount for consistency
        out_list: List[dict] = []
        for b in balances_raw:
            total = b.balance + b.locked
            if hide_dust and total <= 0:
                continue
            d = b.model_dump(mode="json")
            d["total_amount"] = format(total, "f")
            out_list.append(d)
        out = out_list
    if use_rich:
        _print_rich_balance(out)
    else:
        _print_success_stdout(out)


@account_app.command("balance")
def balance(
    ctx: typer.Context,
    hide_dust: bool = typer.Option(
        True,
        "--hide-dust/--no-hide-dust",
        help="Exclude currencies with zero total amount (default: true). Saves token context.",
    ),
    compact: bool = typer.Option(
        True,
        "--compact/--no-compact",
        help="Return compact JSON with total_amount (default: compact).",
    ),
) -> None:
    """List account balances. Compact output includes total_amount (balance + locked). Zero balances are hidden by default."""
    try:
        asyncio.run(
            _balance_impl(
                hide_dust=hide_dust,
                compact=compact,
                use_rich=_is_rich(ctx),
            )
        )
    except AuthError as exc:
        _print_error_stderr(
            exc.error_code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details if exc.details else None,
            exit_code=exc.exit_code,
        )
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
