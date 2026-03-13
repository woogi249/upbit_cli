"""
Withdrawal commands: list, get, krw, coin.

Requires JWT. Compact keeps currency, amount (string), state, txid, uuid.
Withdrawal APIs use no-retry to avoid double-withdrawals. KRW success includes 2FA hint for agents.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from typing import Any, List, Optional

import typer
from pydantic import BaseModel, ConfigDict, field_serializer, model_validator
from rich.console import Console
from rich.table import Table

from upbit_cli.auth import get_credentials
from upbit_cli.http_client import AuthError, UpbitAPIError, request_json_private

withdraw_app = typer.Typer(help="Withdrawals (list, get, krw, coin). Requires API credentials.")


class WithdrawRaw(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=False)
    uuid: Optional[str] = None
    currency: str
    amount: Decimal
    state: Optional[str] = None
    txid: Optional[str] = None

    @field_serializer("amount", when_used="json")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class WithdrawCompact(BaseModel):
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
    def from_raw(cls, raw: WithdrawRaw) -> WithdrawCompact:
        return cls(
            currency=raw.currency,
            amount=raw.amount,
            state=raw.state,
            txid=raw.txid,
            uuid=raw.uuid,
        )


class WithdrawCoinPayload(BaseModel):
    """Strict payload for POST /withdraws/coin. amount must be > 0."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=False)

    currency: str
    net_type: str
    amount: Decimal
    address: str
    secondary_address: Optional[str] = None
    transaction_type: Optional[str] = None  # default | internal

    @field_serializer("amount", when_used="json")
    def _ser_amount(self, v: Decimal) -> str:
        return format(v, "f")

    @model_validator(mode="after")
    def amount_positive(self) -> "WithdrawCoinPayload":
        if self.amount <= 0:
            raise ValueError("amount must be greater than 0")
        return self


def _print_success_stdout(data: Any, suggested_action: Optional[str] = None) -> None:
    payload: dict = {"success": True, "data": data}
    if suggested_action is not None:
        payload["suggested_action"] = suggested_action
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_error_stderr(
    error_code: str,
    message: str,
    *,
    status_code: Optional[int] = None,
    details: Optional[dict] = None,
    suggested_action: Optional[str] = None,
    exit_code: int = 1,
) -> None:
    out = {"success": False, "error_code": error_code, "message": message}
    if status_code is not None:
        out["status_code"] = status_code
    if details:
        out["details"] = details
    if suggested_action is not None:
        out["suggested_action"] = suggested_action
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    sys.stderr.flush()
    raise typer.Exit(code=exit_code)


def _print_rich_list(data: List[Any]) -> None:
    if not data:
        Console().print("No withdrawals")
        return
    t = Table(title="Withdrawals")
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
    raw_json = await request_json_private("GET", "/withdraws", credentials=creds, params=params or None)
    if not isinstance(raw_json, list):
        raise UpbitAPIError(error_code="INVALID_RESPONSE", message="Withdrawals response was not a list.", details={"raw": raw_json})
    items = [WithdrawRaw.model_validate(x) for x in raw_json]
    if compact:
        out = [WithdrawCompact.from_raw(x).model_dump(mode="json") for x in items]
    else:
        out = [x.model_dump(mode="json") for x in items]
    if use_rich:
        _print_rich_list(out)
    else:
        _print_success_stdout(out)


@withdraw_app.command("list")
def list_withdrawals(
    ctx: typer.Context,
    currency: Optional[str] = typer.Option(None, "--currency", "-c"),
    state: Optional[str] = typer.Option(None, "--state"),
    compact: bool = typer.Option(True, "--compact/--no-compact"),
) -> None:
    """List withdrawals."""
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
    raw_json = await request_json_private("GET", "/withdraw", credentials=creds, params={"uuid": uuid_str})
    if compact and isinstance(raw_json, dict):
        out = WithdrawCompact.from_raw(WithdrawRaw.model_validate(raw_json)).model_dump(mode="json")
    else:
        out = raw_json
    if use_rich:
        _print_rich_list([out])
    else:
        _print_success_stdout(out)


@withdraw_app.command("get")
def get_withdrawal(
    ctx: typer.Context,
    uuid_str: str = typer.Option(..., "--uuid"),
    compact: bool = typer.Option(True, "--compact/--no-compact"),
) -> None:
    """Get a single withdrawal by UUID."""
    try:
        asyncio.run(_get_impl(uuid_str=uuid_str, compact=compact, use_rich=_is_rich(ctx)))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code)
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)


async def _withdraw_krw_impl(amount: str, two_factor_type: str) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    raw_json = await request_json_private(
        "POST",
        "/withdraws/krw",
        credentials=creds,
        json_body={"amount": amount, "two_factor_type": two_factor_type},
        allow_retry=False,
    )
    _print_success_stdout(raw_json, suggested_action="await_human_2fa_approval")


@withdraw_app.command("krw")
def withdraw_krw(
    ctx: typer.Context,
    amount: str = typer.Option(..., "--amount", "-a", help="Withdrawal amount (e.g. 10000)."),
    two_factor_type: str = typer.Option(
        ...,
        "--two-factor-type",
        "-t",
        help="2FA channel: kakao or naver. Human must approve in app.",
    ),
) -> None:
    """Request KRW withdrawal. No retries; 2FA must be approved by human. Success includes suggested_action for agents."""
    if two_factor_type not in ("kakao", "naver"):
        _print_error_stderr(
            "VALIDATION_ERROR",
            "two_factor_type must be 'kakao' or 'naver'.",
            exit_code=1,
        )
    try:
        asyncio.run(_withdraw_krw_impl(amount=amount, two_factor_type=two_factor_type))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code, suggested_action="terminate_and_ask_human")
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)


def _withdraw_coin_body(payload: WithdrawCoinPayload) -> dict:
    d = payload.model_dump(mode="json")
    return {k: v for k, v in d.items() if v is not None}


async def _withdraw_coin_impl(
    currency: str,
    net_type: str,
    amount: Decimal,
    address: str,
    secondary_address: Optional[str],
    transaction_type: Optional[str],
) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    payload = WithdrawCoinPayload(
        currency=currency,
        net_type=net_type,
        amount=amount,
        address=address,
        secondary_address=secondary_address,
        transaction_type=transaction_type,
    )
    body = _withdraw_coin_body(payload)
    raw_json = await request_json_private(
        "POST",
        "/withdraws/coin",
        credentials=creds,
        json_body=body,
        allow_retry=False,
    )
    _print_success_stdout(raw_json)


@withdraw_app.command("coin")
def withdraw_coin(
    ctx: typer.Context,
    currency: str = typer.Option(..., "--currency", "-c", help="Currency code (e.g. BTC)."),
    net_type: str = typer.Option(..., "--net-type", "-n", help="Withdrawal network (e.g. BTC, TRX)."),
    amount: str = typer.Option(..., "--amount", "-a", help="Withdrawal amount (must be > 0)."),
    address: str = typer.Option(..., "--address", help="Pre-registered withdrawal address."),
    secondary_address: Optional[str] = typer.Option(None, "--secondary-address", help="Destination tag / memo if required."),
    transaction_type: Optional[str] = typer.Option(
        None,
        "--transaction-type",
        help="default (general) or internal (same-exchange transfer).",
    ),
) -> None:
    """Request digital asset withdrawal. No retries. Amount must be > 0; address must be pre-registered."""
    try:
        amount_dec = Decimal(amount)
    except Exception:
        _print_error_stderr("VALIDATION_ERROR", "amount must be a valid number.", exit_code=1)
    try:
        asyncio.run(
            _withdraw_coin_impl(
                currency=currency,
                net_type=net_type,
                amount=amount_dec,
                address=address,
                secondary_address=secondary_address,
                transaction_type=transaction_type,
            )
        )
    except ValueError as e:
        _print_error_stderr("VALIDATION_ERROR", str(e), exit_code=1)
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code, suggested_action="terminate_and_ask_human")
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)
