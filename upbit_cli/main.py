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
from typing import Any, Optional

import typer

from upbit_cli.commands.configure import configure_app
from upbit_cli.commands.market import market_app
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
) -> None:
    """Print standardized error envelope to stderr. Caller must then raise typer.Exit(code)."""
    payload: dict[str, Any] = {
        "success": False,
        "error_code": error_code,
        "message": message,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if details:
        payload["details"] = details
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
) -> None:
    """Global options applied to all commands. When output is json, stdout is strictly JSON only."""
    ctx.obj = AppConfig(output=output, verbose=verbose)


app.add_typer(market_app, name="market", help="Market data: tickers, orderbooks, candles.")
app.add_typer(configure_app, name="configure", help="Save API credentials to ~/.upbit/config.json.")


def main() -> None:
    """Entrypoint: run the Typer app with a global exception handler."""
    try:
        app()
    except typer.Exit as e:
        raise
    except UpbitAPIError as e:
        _print_error_stderr(
            e.error_code,
            e.message,
            status_code=e.status_code,
            details=e.details if e.details else None,
        )
        raise typer.Exit(e.exit_code)
    except Exception as e:
        _print_error_stderr("UNEXPECTED_ERROR", str(e), details={})
        raise typer.Exit(1)
