"""
Service commands: status (wallet), api-keys.

Requires JWT. api-keys masks access_key in output for security.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from upbit_cli.auth import get_credentials, mask_secret
from upbit_cli.http_client import AuthError, UpbitAPIError, request_json_private

service_app = typer.Typer(help="Service info (wallet status, API keys). Requires API credentials.")


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


def _is_rich(ctx: typer.Context) -> bool:
    root = ctx
    while getattr(root, "parent", None) is not None:
        root = root.parent
    if not getattr(root, "obj", None):
        return False
    out = getattr(root.obj, "output", None)
    return out is not None and getattr(out, "value", str(out)) == "rich"


def _print_rich_table(data: Any, title: str) -> None:
    if isinstance(data, list) and not data:
        Console().print(f"{title}: No data")
        return
    rows = data if isinstance(data, list) else [data]
    if not rows:
        Console().print(f"{title}: No data")
        return
    first = rows[0]
    keys = first.keys() if isinstance(first, dict) else []
    t = Table(title=title)
    for k in keys:
        t.add_column(k)
    for row in rows:
        if isinstance(row, dict):
            t.add_row(*[str(row.get(k, "")) for k in keys])
        else:
            t.add_row(str(row))
    Console().print(t)


async def _status_impl(use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    raw_json = await request_json_private("GET", "/status/wallet", credentials=creds)
    if use_rich:
        _print_rich_table(raw_json if isinstance(raw_json, list) else [raw_json], "Wallet Status")
    else:
        _print_success_stdout(raw_json)


@service_app.command("status")
def status(ctx: typer.Context) -> None:
    """Get deposit/withdrawal wallet service status."""
    try:
        asyncio.run(_status_impl(use_rich=_is_rich(ctx)))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code)
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)


async def _api_keys_impl(use_rich: bool) -> None:
    creds = get_credentials()
    if creds is None:
        raise AuthError(message="Missing API credentials.")
    raw_json = await request_json_private("GET", "/api_keys", credentials=creds)
    items = raw_json if isinstance(raw_json, list) else [raw_json]
    masked: List[dict] = []
    for item in items:
        if not isinstance(item, dict):
            masked.append(item)
            continue
        d = dict(item)
        if "access_key" in d and isinstance(d["access_key"], str):
            d["access_key"] = mask_secret(d["access_key"], visible=0)
        masked.append(d)
    if use_rich:
        _print_rich_table(masked, "API Keys")
    else:
        _print_success_stdout(masked)


@service_app.command("api-keys")
def api_keys(ctx: typer.Context) -> None:
    """List API keys. access_key is masked in output for security."""
    try:
        asyncio.run(_api_keys_impl(use_rich=_is_rich(ctx)))
    except AuthError as e:
        _print_error_stderr(e.error_code, e.message, exit_code=e.exit_code)
    except UpbitAPIError as e:
        _print_error_stderr(e.error_code, e.message, status_code=e.status_code, details=e.details, exit_code=e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), exit_code=1)
