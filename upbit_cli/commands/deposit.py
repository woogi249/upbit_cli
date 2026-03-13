"""
Deposit commands: list, get.

Requires JWT. Compact keeps currency, amount (string), state, txid, uuid.
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

deposit_app = typer.Typer(help="Deposits (list, get). Requires API credentials.")


class DepositRaw(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    uuid: Optional[str] = None
    currency: str
    amount: Decimal
    state: Optional[str] = None
    txid: Optional[str] = None

    @field_serializer("amount", when_used="json")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class DepositCompact(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    currency: str
    amount: Decimal
    state: Optional[str] = None
    txid: Optional[str] = None
    uuid: Optional[str] = None

    @field_serializer("amount", when_used="json")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")

    @classmethod
    def from_raw(cls, raw: DepositRaw) -> DepositCompact:
        return cls(
            currency=raw.currency,
            amount=raw.amount,
            state=raw.state,
            txid=raw.txid,
            uuid=raw.uuid,
        )


def _print_success_stdout(data: Any) -> None:
    print(json.dumps({"success": True, "data": data}, ensure_ascii=False, separators=(",", ":")))


def _print_error_stderr(
    error_code: str, message: str, *, status_code: Optional[int] = None,
    details: Optional[dict] = None, exit_code: int = 1,
) -> None:
    out = {"success": False, "error_code": error_code, "message": message}
    if status_code is not None:
        out["status_code"] = status_code
    if details:
        out["details"] = details
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    sys.stderr.flush()
    raise typer.Exit(code=exit_code)


def _print_rich_list(data: List[Any]) -> None:
    if not data:
        Console().print("No deposits")
        return
    t = Table(title="Deposits")
    for key in data[0].keys():
        t.add_column(key)
    for row in data:
        t.add_row(*[str(row.get(k, "")) for k in data[0].keys()])
    Console().print(t)


def _is_rich(ctx: typer.Context) -> bool:
    root = ctx
    while getattr(root, "parent", None) is not None:
        root = root.parent
    if not getattr(root, "obj", None):
        return False
    out = getattr(root.obj, "output", None)
    return out is not None and getattr(out, "value", str(out)) == "rich"


async def _list_impl(currency: Optional[str], state: Optional[str], compact: bool, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    params: dict = {}
    if currency:
        params["currency"] = currency
    if state:
        params["state"] = state
    raw_json = await request_json_private("GET", "/deposits", credentials=creds, params=params or None)
    if not isinstance(raw_json, list):
        raise UpbitAPIError(error_code="INVALID_RESPONSE", message="Deposits response was not a list.", details={"raw": raw_json})
    items = [DepositRaw.model_validate(x) for x in raw_json]
    if compact:
        out = [DepositCompact.from_raw(x).model_dump(mode="json") for x in items]
    else:
        out = [x.model_dump(mode="json") for x in items]
    if use_rich:
        _print_rich_list(out)
    else:
        _print_success_stdout(out)


@deposit_app.command("list")
def list_deposits(
    ctx: typer.Context,
    currency: Optional[str] = typer.Option(None, "--currency", "-c"),
    state: Optional[str] = typer.Option(None, "--state"),
    compact: bool = typer.Option(True, "--compact/--no-compact"),
) -> None:
    """List deposits."""
    try:
        asyncio.run(_list_impl(currency=currency, state=state, compact=compact, use_rich=_is_rich(ctx)))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code)
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)


async def _get_impl(uuid_str: str, compact: bool, use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    raw_json = await request_json_private("GET", "/deposit", credentials=creds, params={"uuid": uuid_str})
    if compact and isinstance(raw_json, dict):
        out = DepositCompact.from_raw(DepositRaw.model_validate(raw_json)).model_dump(mode="json")
    else:
        out = raw_json
    if use_rich:
        _print_rich_list([out])
    else:
        _print_success_stdout(out)


@deposit_app.command("get")
def get_deposit(
    ctx: typer.Context,
    uuid_str: str = typer.Option(..., "--uuid"),
    compact: bool = typer.Option(True, "--compact/--no-compact"),
) -> None:
    """Get a single deposit by UUID."""
    try:
        asyncio.run(_get_impl(uuid_str=uuid_str, compact=compact, use_rich=_is_rich(ctx)))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code)
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)
