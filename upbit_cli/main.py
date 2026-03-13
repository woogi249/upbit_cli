"""
Global Typer app, CLI entrypoint, and exception handling.

- Global options: --output (json | rich), --verbose.
- When --output json (default), stdout is pure JSON only; Rich is disabled for stdout.
- All unhandled exceptions are converted to a standardized JSON error on stderr and exit with a non-zero code.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Tuple

import typer

from upbit_cli.commands.account import account_app
from upbit_cli.commands.agent import agent_app, _ai_help_content
from upbit_cli.commands.configure import configure_app
from upbit_cli.commands.deposit import deposit_app
from upbit_cli.commands.market import market_app
from upbit_cli.commands.order import order_app
from upbit_cli.commands.service import service_app
from upbit_cli.commands.stream import stream_app
from upbit_cli.commands.withdraw import withdraw_app
from upbit_cli.http_client import UpbitAPIError


class OutputFormat(str, Enum):
    """Output format: json for machines, rich for humans."""

    JSON = "json"
    RICH = "rich"


@dataclass
class AppConfig:
    """Global config stored on Typer context."""

    output: OutputFormat = OutputFormat.JSON
    verbose: bool = False


def print_success_stdout(data: Any) -> None:
    """Print standardized success envelope as pure JSON to stdout. No extra text or ANSI."""
    payload = {"success": True, "data": data}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_error_stderr(
    error_code: str,
    message: str,
    *,
    status_code: Optional[int] = None,
    details: Optional[dict] = None,
    suggested_action: Optional[str] = None,
    retry_after_sec: Optional[int] = None,
) -> None:
    """Print standardized error envelope to stderr. suggested_action helps agents recover."""
    payload: dict[str, Any] = {
        "success": False,
        "error_code": error_code,
        "message": message,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if details:
        payload["details"] = details
    if suggested_action:
        payload["suggested_action"] = suggested_action
    if retry_after_sec is not None:
        payload["retry_after_sec"] = retry_after_sec
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)


app = typer.Typer(
    help="AI-agent-first Upbit CLI: machine-readable JSON, stderr-only errors.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=False)
def global_callback(
    ctx: typer.Context,
    output: OutputFormat = typer.Option(
        OutputFormat.JSON,
        "--output",
        "-o",
        case_sensitive=False,
        help="Output format. Use 'json' for AI agents and piping; 'rich' for human debugging.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Emit extra logs to stderr (never to stdout).",
    ),
    ai_help: bool = typer.Option(
        False,
        "--ai-help",
        help="Print token-optimized CLI usage as JSON for LLM agents, then exit.",
    ),
) -> None:
    """Global options applied to all commands. When output is json, stdout is strictly JSON only."""
    if ai_help:
        print(_ai_help_content())
        raise typer.Exit(0)
    ctx.obj = AppConfig(output=output, verbose=verbose)


app.add_typer(market_app, name="market", help="Market data: tickers, orderbooks, candles.")
app.add_typer(account_app, name="account", help="Account balances (requires API credentials).")
app.add_typer(order_app, name="order", help="Orders: place, list, cancel (requires API credentials).")
app.add_typer(deposit_app, name="deposit", help="Deposits: list, get (requires API credentials).")
app.add_typer(withdraw_app, name="withdraw", help="Withdrawals: list, get (requires API credentials).")
app.add_typer(service_app, name="service", help="Service info: wallet status, API keys (requires API credentials).")
app.add_typer(stream_app, name="stream", help="Real-time WebSocket streams (NDJSON to stdout).")
app.add_typer(agent_app, name="agent", help="Agent integration: schema export, ai-help, MCP.")
app.add_typer(configure_app, name="configure", help="Save API credentials to ~/.upbit/config.json.")


def _suggested_action_for_error(error_code: str, details: Optional[dict]) -> Tuple[Optional[str], Optional[int]]:
    """Return (suggested_action, retry_after_sec) for agent recovery."""
    if error_code == "HTTP_429":
        return "sleep_and_retry", 5
    if error_code == "AUTH_ERROR":
        return "terminate_and_ask_human", None
    if details and ("market" in str(details).lower() or "INVALID" in error_code):
        return "check_market_list_command", None
    if "NETWORK" in error_code or "Connection" in str(details or ""):
        return "retry_after_delay", 2
    return "retry_or_check_docs", None


def main() -> None:
    """Entrypoint: run the Typer app with a global exception handler."""
    try:
        app()
    except typer.Exit as e:
        raise
    except UpbitAPIError as e:
        details = e.details if e.details else None
        action, retry_sec = _suggested_action_for_error(e.error_code, details)
        _print_error_stderr(
            e.error_code,
            e.message,
            status_code=e.status_code,
            details=details,
            suggested_action=action,
            retry_after_sec=retry_sec,
        )
        raise typer.Exit(e.exit_code)
    except Exception as e:
        _print_error_stderr(
            "UNEXPECTED_ERROR",
            str(e),
            details={},
            suggested_action="terminate_and_ask_human",
        )
        raise typer.Exit(1)
